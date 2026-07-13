from django.urls import path
from . import views

app_name = "products"
urlpatterns = [
    path('products/', views.product_list, name='product_list'),
    path('products/<int:product_id>/', views.product_detail, name='product_detail'),

    # TC-024: Reviews
    path('products/<int:product_id>/review/', views.submit_review, name='submit_review'),
    path('reviews/<int:review_id>/respond/', views.respond_to_review, name='respond_to_review'),

    # TC-019: Surplus deals
    path('surplus/', views.surplus_deals, name='surplus_deals'),
    path('surplus/analytics/', views.surplus_analytics, name='surplus_analytics'),

    # TC-020: Recipes & producer stories (customer-facing)
    path('recipes/', views.recipe_list, name='recipe_list'),
    path('recipes/<int:recipe_id>/', views.recipe_detail, name='recipe_detail'),
    path('recipes/saved/', views.saved_recipes_list, name='saved_recipes'),
    path('recipes/<int:recipe_id>/save/', views.toggle_saved_recipe, name='toggle_saved_recipe'),
    path('producer/<int:producer_id>/stories/', views.producer_stories, name='producer_stories'),
    path('stories/', views.all_stories, name='all_stories'),
]