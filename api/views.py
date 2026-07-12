from django.db import connection
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import OrderPayment, OrderProducer
from products.models import Product, ProductCategory

from .permissions import IsProducerOwnerOrReadOnly
from .serializers import (
    OrderPaymentSerializer,
    OrderProducerSerializer,
    ProductCategorySerializer,
    ProductSerializer,
)


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return Response({"status": "unhealthy"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok", "service": "brfn-marketplace"})


class ProductCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductCategory.objects.filter(is_active=True).order_by("order", "name")
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.AllowAny]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsProducerOwnerOrReadOnly]

    def get_queryset(self):
        queryset = (
            Product.objects.filter(is_active=True)
            .select_related("producer__user", "category")
            .prefetch_related("allergens")
        )
        search = self.request.query_params.get("search", "").strip()
        category = self.request.query_params.get("category", "").strip()
        organic = self.request.query_params.get("organic", "").strip().lower()
        available = self.request.query_params.get("available", "").strip().lower()
        surplus = self.request.query_params.get("surplus", "").strip().lower()

        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category:
            queryset = queryset.filter(Q(category__slug=category) | Q(category_id=category))
        if organic in {"1", "true", "yes"}:
            queryset = queryset.filter(is_organic=True)
        if available in {"1", "true", "yes"}:
            queryset = queryset.filter(availability="available", stock_quantity__gt=0)
        if surplus in {"1", "true", "yes"}:
            queryset = queryset.filter(surplus_deal__is_active=True)
        return queryset.order_by("category__order", "name")

    def perform_create(self, serializer):
        profile = getattr(self.request.user, "producer_profile", None)
        if profile is None:
            raise PermissionDenied("Only registered producers can create products.")
        serializer.save(producer=profile)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = OrderPayment.objects.prefetch_related(
            "producer_orders__producer",
            "producer_orders__order_items",
        )
        if self.request.user.is_staff or self.request.user.role == "system_admin":
            return queryset
        return queryset.filter(user=self.request.user)


class ProducerOrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderProducerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role != "producer" or not hasattr(
            self.request.user, "producer_profile"
        ):
            return OrderProducer.objects.none()
        return OrderProducer.objects.filter(
            producer=self.request.user.producer_profile,
            payment__payment_status="paid",
        ).select_related("payment", "producer").prefetch_related("order_items").order_by("-created_at")
