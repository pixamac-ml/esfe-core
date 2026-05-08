from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db.models import Q
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from accounts.dashboards.helpers import get_user_branch, is_manager
from branches.models import Branch
from shop.forms import ShopCounterOrderForm, ShopPaymentForm, ShopProductForm, ShopPublicOrderForm, ShopStockInForm
from shop.models import ShopOrder, ShopPayment, ShopProduct, ShopSequence, ShopStockMovement
from shop.services.shop_service import (
    create_counter_order,
    create_shop_payment,
    create_student_required_order,
    deliver_order,
    get_required_shop_context,
    get_manager_shop_context,
    mark_order_ready,
    next_shop_reference,
    validate_shop_payment,
)
from students.models import Student


def manager_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            return HttpResponse("Non autorise", status=403)
        branch = get_user_branch(request.user)
        if not branch:
            return HttpResponse("Annexe non trouvee", status=403)
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def manager_shop_redirect(request):
    if not request.headers.get("HX-Request"):
        return redirect(f"{reverse('accounts:manager_dashboard')}?section=boutique")
    response = HttpResponse("")
    response["HX-Redirect"] = f"{reverse('accounts:manager_dashboard')}?section=boutique"
    return response


def render_manager_shop_panel(request, *, product_form=None, stock_form=None, counter_order_form=None, status=200):
    shop_context = get_manager_shop_context(request.branch)
    context = {
        **shop_context,
        "shop_product_form": product_form or ShopProductForm(),
        "shop_stock_form": stock_form or ShopStockInForm(branch=request.branch),
        "shop_counter_order_form": counter_order_form or ShopCounterOrderForm(branch=request.branch),
    }
    response = render(request, "shop/partials/manager_shop_panel.html", context)
    response.status_code = status
    return response


def get_branch_public_shop_identifier(branch):
    slug = (getattr(branch, "slug", "") or "").strip()
    if slug:
        return slug
    code = (getattr(branch, "code", "") or "").strip().lower()
    if code:
        return code
    return slugify(getattr(branch, "name", "") or "")


def resolve_public_shop_branch(identifier):
    normalized = (identifier or "").strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    branches = list(Branch.objects.filter(is_active=True))
    for branch in branches:
        if (branch.slug or "").strip().lower() == lowered:
            return branch
        if (branch.code or "").strip().lower() == lowered:
            return branch
        if slugify(branch.name or "") == lowered:
            return branch
    return None


def resolve_public_shop_student(branch, identifier):
    value = (identifier or "").strip()
    if not value:
        return None
    queryset = (
        Student.objects
        .select_related("user", "inscription__candidature")
        .filter(
            is_active=True,
            inscription__candidature__branch=branch,
            inscription__candidature__is_deleted=False,
            inscription__is_archived=False,
        )
    )
    query = Q(user__username__iexact=value) | Q(matricule__iexact=value)
    if value.isdigit():
        query |= Q(user__id=int(value))
    return queryset.filter(query).first()


@require_GET
def public_shop_home(request):
    if request.user.is_authenticated:
        branch = get_user_branch(request.user)
        identifier = get_branch_public_shop_identifier(branch) if branch else ""
        if identifier:
            return redirect(f"/shop/{identifier}/")
    branch = Branch.objects.filter(is_active=True).order_by("name").first()
    identifier = get_branch_public_shop_identifier(branch) if branch else ""
    if identifier:
        return redirect(f"/shop/{identifier}/")
    return HttpResponse("Aucune annexe boutique disponible.", status=404)


def render_public_shop_catalog(request, *, branch, status=200, form=None, selected_product=None):
    selected_category = (request.GET.get("category") or "").strip()
    products = (
        ShopProduct.objects
        .filter(branch=branch, is_active=True)
        .prefetch_related("programmes", "variants")
        .order_by("-is_required", "category", "name")
    )
    if selected_category:
        products = products.filter(category=selected_category)
    products = list(products)
    categories = [
        {"value": value, "label": label, "count": sum(1 for product in products if product.category == value)}
        for value, label in ShopProduct.CATEGORY_CHOICES
    ]
    response = render(
        request,
        "shop/public_catalog.html",
        {
            "branch": branch,
            "products": products,
            "selected_category": selected_category,
            "categories": categories,
            "has_student_profile": bool(getattr(request.user, "is_authenticated", False) and getattr(request.user, "student_profile", None)),
            "branch_public_identifier": get_branch_public_shop_identifier(branch),
            "public_order_form": form or ShopPublicOrderForm(),
            "public_order_product_id": selected_product.id if selected_product else None,
            "public_order_product": selected_product,
            "order_success_reference": (request.GET.get("ordered") or "").strip(),
            "catalog_stats": {
                "products": len(products),
                "required": sum(1 for product in products if product.is_required),
                "available": sum(1 for product in products if product.current_stock > 0),
                "low_stock": sum(1 for product in products if product.is_low_stock),
            },
        },
    )
    response.status_code = status
    return response


@require_GET
def public_shop_catalog(request, branch_slug):
    branch = resolve_public_shop_branch(branch_slug)
    if not branch:
        raise Http404("Annexe boutique introuvable.")
    return render_public_shop_catalog(request, branch=branch)


@require_POST
def public_shop_product_order(request, branch_slug, pk):
    branch = resolve_public_shop_branch(branch_slug)
    if not branch:
        raise Http404("Annexe boutique introuvable.")
    product = get_object_or_404(ShopProduct, pk=pk, branch=branch, is_active=True)
    form = ShopPublicOrderForm(request.POST)
    if not form.is_valid():
        return render_public_shop_catalog(request, branch=branch, status=400, form=form, selected_product=product)

    student_record = None
    if form.cleaned_data["buyer_type"] == "student":
        student_record = resolve_public_shop_student(branch, form.cleaned_data["student_identifier"])
        if not student_record:
            form.add_error("student_identifier", "Aucun etudiant actif ne correspond a cet identifiant dans cette annexe.")
            return render_public_shop_catalog(request, branch=branch, status=400, form=form, selected_product=product)

    actor = request.user if getattr(request.user, "is_authenticated", False) else None
    order, _payment = create_counter_order(
        branch=branch,
        product=product,
        quantity=form.cleaned_data["quantity"],
        payment_method=form.cleaned_data["payment_method"],
        created_by=actor,
        student=student_record.user if student_record else None,
        customer_name=form.cleaned_data.get("customer_name", ""),
        customer_email=form.cleaned_data.get("customer_email", ""),
        customer_phone=form.cleaned_data.get("customer_phone", ""),
    )
    return redirect(f"/shop/{get_branch_public_shop_identifier(branch)}/?ordered={order.reference}")


@login_required
@require_GET
def student_required_modal(request):
    context = get_required_shop_context(request.user)
    return render(request, "shop/partials/student_required_modal.html", context)


@login_required
@require_POST
def student_create_required_order(request):
    product_ids = request.POST.getlist("product_ids")
    order = create_student_required_order(request.user, product_ids, created_by=request.user)
    if not order:
        return HttpResponse("Aucun article selectionne.", status=400)
    return redirect(f"/shop/student/order/{order.pk}/")


@login_required
@require_GET
def student_order_detail(request, pk):
    order = get_object_or_404(
        ShopOrder.objects.prefetch_related("items", "items__product", "items__variant", "payments"),
        pk=pk,
        student=request.user,
    )
    return render(
        request,
        "shop/partials/student_order_detail.html",
        {
            "order": order,
            "payment_form": ShopPaymentForm(),
            "has_pending_payment": order.payments.filter(status=ShopPayment.STATUS_PENDING).exists(),
        },
    )


@login_required
@require_POST
def student_order_pay(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, student=request.user)
    form = ShopPaymentForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "shop/partials/student_order_detail.html",
            {
                "order": order,
                "payment_form": form,
                "has_pending_payment": order.payments.filter(status=ShopPayment.STATUS_PENDING).exists(),
            },
            status=400,
        )
    if order.payments.filter(status=ShopPayment.STATUS_PENDING).exists():
        return redirect(f"/shop/student/order/{order.pk}/")
    method = form.cleaned_data["method"]
    auto_validate = False
    payment = create_shop_payment(order, order.balance or order.total_amount, method, request.user, auto_validate=auto_validate)
    if not auto_validate:
        order.status = ShopOrder.STATUS_PENDING_PAYMENT
        order.save(update_fields=["status", "updated_at"])
    return redirect(f"/shop/student/order/{order.pk}/")


@login_required
@require_GET
def shop_payment_receipt(request, pk):
    payment = get_object_or_404(ShopPayment.objects.select_related("order"), pk=pk)
    manager_branch = get_user_branch(request.user) if is_manager(request.user) else None
    can_view_as_manager = bool(manager_branch and manager_branch.pk == payment.order.branch_id)
    if payment.order.student_id != request.user.id and not request.user.is_staff and not can_view_as_manager:
        return HttpResponse("Non autorise", status=403)
    if not payment.receipt_pdf:
        raise Http404("Recu indisponible.")
    return FileResponse(payment.receipt_pdf.open("rb"), as_attachment=True, filename=f"recu-boutique-{payment.receipt_number}.pdf")


@manager_required
@require_POST
def manager_product_create(request):
    form = ShopProductForm(request.POST, request.FILES)
    if not form.is_valid():
        return render_manager_shop_panel(request, product_form=form, status=400)
    product = form.save(commit=False)
    product.branch = request.branch
    product.save()
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, product_form=ShopProductForm())
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_product_delete(request, pk):
    product = get_object_or_404(ShopProduct, pk=pk, branch=request.branch)
    if product.order_items.exists() or product.stock_movements.exists():
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
    else:
        product.delete()
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_stock_in(request):
    form = ShopStockInForm(request.POST, branch=request.branch)
    if not form.is_valid():
        return render_manager_shop_panel(request, stock_form=form, status=400)
    ShopStockMovement.objects.create(
        branch=request.branch,
        product=form.cleaned_data["product"],
        movement_type=ShopStockMovement.TYPE_IN,
        quantity=form.cleaned_data["quantity"],
        reference=next_shop_reference(request.branch, ShopSequence.TYPE_STOCK),
        notes=form.cleaned_data.get("notes", ""),
        created_by=request.user,
    )
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, stock_form=ShopStockInForm(branch=request.branch))
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_counter_order_create(request):
    form = ShopCounterOrderForm(request.POST, branch=request.branch)
    if not form.is_valid():
        return render_manager_shop_panel(request, counter_order_form=form, status=400)
    student = form.cleaned_data.get("student")
    create_counter_order(
        branch=request.branch,
        product=form.cleaned_data["product"],
        quantity=form.cleaned_data["quantity"],
        payment_method=form.cleaned_data["payment_method"],
        created_by=request.user,
        student=student,
        customer_name=form.cleaned_data.get("customer_name", ""),
        customer_email=form.cleaned_data.get("customer_email", ""),
        customer_phone=form.cleaned_data.get("customer_phone", ""),
    )
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, counter_order_form=ShopCounterOrderForm(branch=request.branch))
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_payment_validate(request, pk):
    payment = get_object_or_404(ShopPayment, pk=pk, order__branch=request.branch)
    validate_shop_payment(payment, user=request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_order_mark_ready(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, branch=request.branch)
    mark_order_ready(order, request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_order_deliver(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, branch=request.branch)
    deliver_order(order, request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)
