from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from customers.forms import CustomerLoginForm, RestaurantLoginForm


app_name = 'customers'

urlpatterns = [
    path("customer/login", views.CustomerLoginView.as_view(), name='login'),

    path("customer/register/", views.register_customer, name="register"),

    # Backward compatibility: redirect old URLs to unified register with ?role= parameter
    path("community/register/", views.register_customer, name="register_community"),
    path("restaurant/register/", views.register_customer, name="register_restaurant"),

    path("community/login/", views.CustomerLoginView.as_view(), name='community_login'),

    path('restaurant/login/', views.RestaurantLoginView.as_view(), name='restaurant_login'),

    # Cart operations
    path("customer/cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("customer/cart/", views.view_cart, name="view_cart"),
    path("customer/cart/remove/<int:item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("customer/cart/update/<int:item_id>/", views.update_cart_item, name="update_cart_item"),
    path("customer/profile", views.customer_profile_view, name="profile"),
    path("customer/personal-info", views.customer_personal_info_view, name="personal_info"),
]