from django.test import TestCase
from django.urls import reverse
from decimal import Decimal
from datetime import timedelta

from mainApp.models import RegularUser
from django.utils import timezone

from mainApp.models import Notification
from orders.models import (
    OrderInstance, OrderPayment, OrderProducer, RecurringOrder, RecurringOrderItem,
)
from orders.tasks import generate_recurring_order_instances
from products.models import Product


class RoleScopedOrderVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.producer_user = RegularUser.objects.create_user(
            username='visibility-producer', password='test-pass',
            role=RegularUser.Role.PRODUCER,
        )
        cls.other_producer_user = RegularUser.objects.create_user(
            username='other-producer', password='test-pass',
            role=RegularUser.Role.PRODUCER,
        )
        cls.buyers = []
        for role in (
            RegularUser.Role.CUSTOMER,
            RegularUser.Role.COMMUNITY_MEMBER,
            RegularUser.Role.RESTAURANT,
        ):
            buyer = RegularUser.objects.create_user(
                username=f'visibility-{role}', password='test-pass', role=role,
            )
            payment = OrderPayment.objects.create(
                user=buyer, payment_status='paid', total_amount=Decimal('20.00'),
            )
            OrderProducer.objects.create(
                payment=payment,
                producer=cls.producer_user.producer_profile,
                producer_subtotal=Decimal('20.00'),
                order_status='confirmed',
            )
            cls.buyers.append((buyer, payment))

        cls.unpaid = OrderPayment.objects.create(
            user=cls.buyers[0][0], payment_status='pending', total_amount=Decimal('99.00'),
        )
        OrderProducer.objects.create(
            payment=cls.unpaid,
            producer=cls.producer_user.producer_profile,
            producer_subtotal=Decimal('99.00'),
        )
        cls.admin = RegularUser.objects.create_superuser(
            username='visibility-admin', password='test-pass', email='admin@example.test',
        )

    def test_each_customer_role_sees_only_its_own_paid_order(self):
        url = reverse('mainApp:orders:order_history')
        for buyer, payment in self.buyers:
            with self.subTest(role=buyer.role):
                self.client.force_login(buyer)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                visible_ids = [entry['order'].id for entry in response.context['orders_data']]
                self.assertEqual(visible_ids, [payment.id])
                self.client.logout()

    def test_producer_sees_paid_suborders_for_only_its_profile(self):
        self.client.force_login(self.producer_user)
        response = self.client.get(reverse('mainApp:producers:incoming_orders'))
        self.assertEqual(response.status_code, 200)
        visible = [entry['order'] for entry in response.context['page_obj'].object_list]
        self.assertEqual(len(visible), 3)
        self.assertTrue(all(order.producer == self.producer_user.producer_profile for order in visible))
        self.assertTrue(all(order.payment.payment_status == 'paid' for order in visible))

        self.client.force_login(self.other_producer_user)
        response = self.client.get(reverse('mainApp:producers:incoming_orders'))
        self.assertEqual(list(response.context['page_obj'].object_list), [])

    def test_administrator_can_audit_all_paid_customer_orders(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('mainApp:orders:order_history'))
        self.assertEqual(response.status_code, 200)
        visible_ids = {entry['order'].id for entry in response.context['orders_data']}
        self.assertEqual(visible_ids, {payment.id for _, payment in self.buyers})

    def test_producer_order_history_redirects_to_incoming_orders(self):
        self.client.force_login(self.producer_user)
        response = self.client.get(reverse('mainApp:orders:order_history'))
        self.assertRedirects(response, reverse('mainApp:producers:incoming_orders'))


class RecurringOrderGenerationTests(TestCase):
    def test_due_restaurant_order_creates_instance_and_notifies_its_producer(self):
        producer_user = RegularUser.objects.create_user(
            username='recurring-producer', role=RegularUser.Role.PRODUCER,
        )
        producer_user.producer_profile.business_name = 'Recurring Farm'
        producer_user.producer_profile.lead_time_hours = 48
        producer_user.producer_profile.save()
        restaurant = RegularUser.objects.create_user(
            username='recurring-restaurant', role=RegularUser.Role.RESTAURANT,
        )
        product = Product.objects.create(
            name='Recurring Carrots', description='Test product', price=Decimal('2.50'),
            unit='kg', stock_quantity=10, producer=producer_user.producer_profile,
        )
        scheduled = timezone.localdate() + timedelta(days=1)
        recurring = RecurringOrder.objects.create(
            customer=restaurant, status='active', recurrence='weekly',
            recurrence_day='monday', delivery_day='wednesday',
            next_scheduled_date=scheduled,
        )
        RecurringOrderItem.objects.create(
            recurring_order=recurring, product=product,
            producer=producer_user.producer_profile,
            product_name=product.name, quantity=2, unit=product.unit,
        )

        result = generate_recurring_order_instances()

        self.assertEqual(result, 'Created 1 recurring order instances')
        self.assertTrue(OrderInstance.objects.filter(
            recurring_order=recurring, scheduled_date=scheduled,
        ).exists())
        self.assertTrue(Notification.objects.filter(
            user=producer_user, title='Upcoming Recurring Order',
            message__contains='Recurring Carrots',
        ).exists())
