from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from customers.models import Cart, CartItem
from mainApp.models import Notification, ProducerProfile, RegularUser
from orders.models import OrderPayment, OrderProducer
from products.models import Product, ProductCategory, SurplusDeal


class MarketplaceApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.producer_user = RegularUser.objects.create_user(
            username="producer-one",
            email="producer@example.test",
            password="StrongPass!2026",
            role=RegularUser.Role.PRODUCER,
            phone_number="07000000001",
        )
        cls.producer = cls.producer_user.producer_profile
        cls.producer.business_name = "Harbourside Farm"
        cls.producer.lead_time_hours = 48
        cls.producer.save()
        cls.other_producer_user = RegularUser.objects.create_user(
            username="producer-two",
            email="producer2@example.test",
            password="StrongPass!2026",
            role=RegularUser.Role.PRODUCER,
            phone_number="07000000002",
        )
        cls.other_producer = cls.other_producer_user.producer_profile
        cls.other_producer.business_name = "Avon Dairy"
        cls.other_producer.save()
        cls.customer = RegularUser.objects.create_user(
            username="customer-one",
            email="customer@example.test",
            password="StrongPass!2026",
            role=RegularUser.Role.CUSTOMER,
            phone_number="07000000003",
        )
        cls.other_customer = RegularUser.objects.create_user(
            username="customer-two",
            email="customer2@example.test",
            password="StrongPass!2026",
            role=RegularUser.Role.CUSTOMER,
            phone_number="07000000004",
        )
        cls.category = ProductCategory.objects.create(
            name="Vegetables",
            slug="vegetables",
        )
        cls.product = Product.objects.create(
            name="Organic Carrots",
            description="Fresh carrots harvested near Bristol.",
            price=Decimal("2.50"),
            unit="kg",
            stock_quantity=25,
            producer=cls.producer,
            category=cls.category,
            is_organic=True,
        )

    def test_health_endpoint_is_public(self):
        response = self.client.get(reverse("api-health"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")

    def test_product_list_is_public_and_searchable(self):
        response = self.client.get(reverse("api-products-list"), {"search": "carrot"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["producer_name"], "Harbourside Farm")

    def test_inactive_products_are_not_exposed(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        response = self.client.get(reverse("api-products-list"))
        self.assertEqual(response.data["count"], 0)

    def test_anonymous_user_cannot_create_product(self):
        response = self.client.post(reverse("api-products-list"), {}, format="json")
        self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    def test_producer_can_create_product_and_is_set_as_owner(self):
        self.client.force_authenticate(self.producer_user)
        response = self.client.post(
            reverse("api-products-list"),
            {
                "name": "Rainbow Chard",
                "description": "Seasonal leafy greens.",
                "price": "3.20",
                "unit": "bunch",
                "stock_quantity": 15,
                "low_stock_threshold": 4,
                "availability": "available",
                "is_organic": True,
                "category": self.category.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = Product.objects.get(name="Rainbow Chard")
        self.assertEqual(created.producer, self.producer)

    def test_customer_cannot_create_product(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(reverse("api-products-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_producer_cannot_change_another_producers_product(self):
        self.client.force_authenticate(self.other_producer_user)
        response = self.client.patch(
            reverse("api-products-detail", args=[self.product.pk]),
            {"price": "1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_order_endpoint_is_scoped_to_logged_in_customer(self):
        OrderPayment.objects.create(user=self.customer, payment_status="paid", total_amount="10.00")
        OrderPayment.objects.create(user=self.other_customer, payment_status="paid", total_amount="99.00")
        self.client.force_authenticate(self.customer)
        response = self.client.get(reverse("api-orders-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(Decimal(response.data["results"][0]["total_amount"]), Decimal("10.00"))

    def test_producer_order_endpoint_is_scoped_to_logged_in_producer(self):
        payment = OrderPayment.objects.create(
            user=self.customer,
            payment_status="paid",
            total_amount="20.00",
        )
        OrderProducer.objects.create(
            payment=payment,
            producer=self.producer,
            producer_subtotal=Decimal("20.00"),
        )
        OrderProducer.objects.create(
            payment=payment,
            producer=self.other_producer,
            producer_subtotal=Decimal("5.00"),
        )
        self.client.force_authenticate(self.producer_user)
        response = self.client.get(reverse("api-producer-orders-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["producer_name"], "Harbourside Farm")


class MarketplaceBusinessRuleTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.producer_user = RegularUser.objects.create_user(
            username="rule-producer",
            password="StrongPass!2026",
            role=RegularUser.Role.PRODUCER,
            phone_number="07000000005",
        )
        cls.producer = cls.producer_user.producer_profile
        cls.producer.business_name = "Rule Farm"
        cls.producer.save()
        cls.customer = RegularUser.objects.create_user(
            username="rule-customer",
            password="StrongPass!2026",
            role=RegularUser.Role.CUSTOMER,
            phone_number="07000000006",
        )
        cls.category = ProductCategory.objects.create(name="Dairy", slug="dairy")
        cls.product = Product.objects.create(
            name="Fresh Milk",
            description="Pasteurised whole milk.",
            price="2.00",
            unit="litre",
            stock_quantity=12,
            low_stock_threshold=10,
            producer=cls.producer,
            category=cls.category,
        )

    def test_commission_is_five_percent_and_payout_is_ninety_five_percent(self):
        payment = OrderPayment.objects.create(user=self.customer, total_amount="100.00")
        producer_order = OrderProducer.objects.create(
            payment=payment,
            producer=self.producer,
            producer_subtotal=Decimal("100.00"),
        )
        self.assertEqual(producer_order.commission, Decimal("5.00"))
        self.assertEqual(producer_order.producer_payout, Decimal("95.00"))

    def test_low_stock_crossing_creates_notification(self):
        self.assertTrue(self.product.deduct_stock(3))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 9)
        self.assertTrue(
            Notification.objects.filter(user=self.producer_user, title="Low Stock Alert").exists()
        )

    def test_stock_cannot_be_deducted_below_zero(self):
        self.assertFalse(self.product.deduct_stock(99))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 12)

    def test_cart_groups_multi_vendor_items(self):
        other_user = RegularUser.objects.create_user(
            username="cart-producer-two",
            password="StrongPass!2026",
            role=RegularUser.Role.PRODUCER,
            phone_number="07000000007",
        )
        other_producer = other_user.producer_profile
        other_producer.business_name = "Second Farm"
        other_producer.save()
        other_product = Product.objects.create(
            name="Yoghurt",
            description="Natural yoghurt.",
            price="3.00",
            unit="each",
            stock_quantity=5,
            producer=other_producer,
            category=self.category,
        )
        cart = self.customer.cart
        CartItem.objects.create(cart=cart, product=self.product, quantity=2, unit_price="2.00")
        CartItem.objects.create(cart=cart, product=other_product, quantity=1, unit_price="3.00")
        self.assertEqual(len(cart.get_items_by_producer()), 2)
        self.assertEqual(cart.total_amount(), Decimal("7.00"))

    def test_surplus_discount_is_calculated_and_validated(self):
        deal = SurplusDeal(
            product=self.product,
            producer=self.producer,
            discount_percent=30,
            original_price=Decimal("2.00"),
            discounted_price=Decimal("0.00"),
            expires_at=timezone.now() + timedelta(hours=48),
        )
        deal.full_clean()
        self.assertEqual(deal.discounted_price, Decimal("1.40"))

        deal.discount_percent = 70
        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_product_availability_respects_stock_and_season(self):
        self.product.season_start = 1
        self.product.season_end = 2
        self.assertFalse(self.product.is_available)
        self.product.season_start = None
        self.product.season_end = None
        self.assertTrue(self.product.is_available)
        self.product.stock_quantity = 0
        self.assertFalse(self.product.is_available)

    def test_weak_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_password("123")

    def test_user_without_default_address_has_no_postcode(self):
        self.assertIsNone(self.customer.default_address_postcode)
