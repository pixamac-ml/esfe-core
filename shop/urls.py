from django.urls import path

from shop import views


app_name = "shop"

urlpatterns = [
    path("student/required-modal/", views.student_required_modal, name="student_required_modal"),
    path("student/order/create-required/", views.student_create_required_order, name="student_create_required_order"),
    path("student/order/<int:pk>/", views.student_order_detail, name="student_order_detail"),
    path("student/order/<int:pk>/pay/", views.student_order_pay, name="student_order_pay"),
    path("payment/<int:pk>/receipt/", views.shop_payment_receipt, name="payment_receipt"),
    path("manager/product/create/", views.manager_product_create, name="manager_product_create"),
    path("manager/stock/in/", views.manager_stock_in, name="manager_stock_in"),
    path("manager/payment/<int:pk>/validate/", views.manager_payment_validate, name="manager_payment_validate"),
    path("manager/order/<int:pk>/deliver/", views.manager_order_deliver, name="manager_order_deliver"),
]
