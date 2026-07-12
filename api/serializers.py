from rest_framework import serializers

from orders.models import OrderItem, OrderPayment, OrderProducer
from products.models import Product, ProductCategory


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "slug", "description"]


class ProductSerializer(serializers.ModelSerializer):
    producer_name = serializers.CharField(source="producer.business_name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    allergens = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field="display_name",
    )
    is_in_season = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    image_url = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "unit",
            "stock_quantity",
            "low_stock_threshold",
            "availability",
            "harvest_date",
            "is_organic",
            "season_start",
            "season_end",
            "is_in_season",
            "is_low_stock",
            "category",
            "category_name",
            "producer_name",
            "allergens",
            "allergen_statement",
            "image_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("season_start", getattr(self.instance, "season_start", None))
        end = attrs.get("season_end", getattr(self.instance, "season_end", None))
        if bool(start) != bool(end):
            raise serializers.ValidationError(
                "Season start and season end must either both be set or both be empty."
            )
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "product_price", "quantity", "unit", "line_total"]


class OrderProducerSerializer(serializers.ModelSerializer):
    producer_name = serializers.CharField(source="producer.business_name", read_only=True)
    order_items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = OrderProducer
        fields = [
            "id",
            "producer_name",
            "order_status",
            "delivered_by",
            "food_mile_distance",
            "producer_subtotal",
            "commission",
            "producer_payout",
            "is_bulk_order",
            "order_items",
        ]


class OrderPaymentSerializer(serializers.ModelSerializer):
    producer_orders = OrderProducerSerializer(many=True, read_only=True)

    class Meta:
        model = OrderPayment
        fields = [
            "id",
            "payment_status",
            "total_amount",
            "shipping_address",
            "global_delivery_notes",
            "special_instructions",
            "created_at",
            "producer_orders",
        ]

