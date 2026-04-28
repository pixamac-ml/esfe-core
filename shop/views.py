from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from accounts.dashboards.helpers import get_user_branch, is_manager
from shop.forms import ShopPaymentForm, ShopProductForm, ShopStockInForm
from shop.models import ShopOrder, ShopPayment, ShopProduct, ShopSequence, ShopStockMovement
from shop.services.shop_service import (
    create_shop_payment,
    create_student_required_order,
    deliver_order,
    get_required_shop_context,
    next_shop_reference,
    validate_shop_payment,
)


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
    return redirect("shop:student_order_detail", pk=order.pk)


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
        return redirect("shop:student_order_detail", pk=order.pk)
    method = form.cleaned_data["method"]
    auto_validate = False
    payment = create_shop_payment(order, order.balance or order.total_amount, method, request.user, auto_validate=auto_validate)
    if not auto_validate:
        order.status = ShopOrder.STATUS_PENDING_PAYMENT
        order.save(update_fields=["status", "updated_at"])
    return redirect("shop:student_order_detail", pk=order.pk)


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
    form = ShopProductForm(request.POST)
    if not form.is_valid():
        return HttpResponse("Article invalide.", status=400)
    product = form.save(commit=False)
    product.branch = request.branch
    product.save()
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_stock_in(request):
    form = ShopStockInForm(request.POST, branch=request.branch)
    if not form.is_valid():
        return HttpResponse("Stock invalide.", status=400)
    ShopStockMovement.objects.create(
        branch=request.branch,
        product=form.cleaned_data["product"],
        movement_type=ShopStockMovement.TYPE_IN,
        quantity=form.cleaned_data["quantity"],
        reference=next_shop_reference(request.branch, ShopSequence.TYPE_STOCK),
        notes=form.cleaned_data.get("notes", ""),
        created_by=request.user,
    )
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_payment_validate(request, pk):
    payment = get_object_or_404(ShopPayment, pk=pk, order__branch=request.branch)
    validate_shop_payment(payment, user=request.user)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_order_deliver(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, branch=request.branch)
    deliver_order(order, request.user)
    return manager_shop_redirect(request)
