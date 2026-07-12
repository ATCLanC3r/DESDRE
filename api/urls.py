from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    HealthView,
    OrderViewSet,
    ProducerOrderViewSet,
    ProductCategoryViewSet,
    ProductViewSet,
)


router = DefaultRouter()
router.register("products", ProductViewSet, basename="api-products")
router.register("categories", ProductCategoryViewSet, basename="api-categories")
router.register("orders", OrderViewSet, basename="api-orders")
router.register("producer-orders", ProducerOrderViewSet, basename="api-producer-orders")

urlpatterns = [
    path("health/", HealthView.as_view(), name="api-health"),
    path("", include(router.urls)),
]
