from celery import shared_task
from django.utils import timezone
from orders.models import OrderPayment
import logging
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_orders():
    now = timezone.now()

    expired_orders = OrderPayment.objects.filter(
        payment_status='pending',
        expires_at__lt=now
    )

    count = expired_orders.count()
    expired_orders.delete()

    return f"Deleted {count} expired orders"


# =============================================================================
# TC-018 — Generate recurring order instances
# =============================================================================

@shared_task
def generate_recurring_order_instances():
    """
    Daily job: create OrderInstance records for active RecurringOrders whose
    next_scheduled_date falls within the maximum producer lead-time window.
    """
    from datetime import date, timedelta
    from django.db import models as db_models
    from orders.models import RecurringOrder, OrderInstance, OrderInstanceItem
    from mainApp.models import ProducerProfile, Notification

    today = date.today()

    # Repair templates created before schedule initialisation was implemented.
    weekday_numbers = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    for recurring in RecurringOrder.objects.filter(status='active', next_scheduled_date__isnull=True):
        target = weekday_numbers.get(recurring.recurrence_day, 0)
        days_ahead = (target - today.weekday()) % 7 or 7
        recurring.next_scheduled_date = today + timedelta(days=days_ahead)
        recurring.save(update_fields=['next_scheduled_date'])

    active_orders = RecurringOrder.objects.filter(
        status='active', next_scheduled_date__isnull=False,
    ).select_related('customer').prefetch_related('items__product', 'items__producer')

    created = 0
    for ro in active_orders:
        # Respect the maximum lead time across all producers in this template
        producer_ids = ro.items.values_list('producer_id', flat=True)
        max_lead_hours = (
            ProducerProfile.objects.filter(id__in=producer_ids)
            .aggregate(m=db_models.Max('lead_time_hours'))['m']
        ) or 48
        lead_window = today + timedelta(days=(max_lead_hours + 23) // 24)

        if ro.next_scheduled_date > lead_window:
            continue

        # Avoid duplicate instances for the same scheduled date
        if OrderInstance.objects.filter(
            recurring_order=ro,
            scheduled_date=ro.next_scheduled_date
        ).exists():
            continue

        instance = OrderInstance.objects.create(
            recurring_order=ro,
            scheduled_date=ro.next_scheduled_date,
            status='pending',
        )

        # Copy template items — skip unavailable products and collect alerts
        unavailable_names = []
        for template_item in ro.items.select_related('product'):
            product = template_item.product
            if not product or product.availability != 'available' or not product.is_active:
                unavailable_names.append(template_item.product_name)
                continue
            OrderInstanceItem.objects.create(
                instance=instance,
                product=product,
                product_name=template_item.product_name,
                quantity=template_item.quantity,
                unit=template_item.unit,
            )

        # Notify customer of unavailable items
        if unavailable_names:
            Notification.objects.create(
                user=ro.customer,
                notification_type=Notification.TYPE_SYSTEM,
                title="Recurring Order — Products Unavailable",
                message=(
                    f"The following item(s) in your recurring order are currently "
                    f"unavailable and were skipped: {', '.join(unavailable_names)}."
                ),
                link=f'/orders/recurring/{ro.id}/',
            )

        # Advance next_scheduled_date
        if ro.recurrence == 'weekly':
            ro.next_scheduled_date += timedelta(weeks=1)
        else:
            ro.next_scheduled_date += timedelta(weeks=2)
        ro.save(update_fields=['next_scheduled_date'])

        _send_recurring_notification(ro, instance)
        _notify_recurring_producers(ro, instance)
        created += 1

    return f"Created {created} recurring order instances"


def _send_recurring_notification(recurring_order, instance):
    """Send both an in-app notification and an email to the restaurant."""
    from django.core.mail import send_mail
    from django.conf import settings
    from mainApp.models import Notification

    user = recurring_order.customer
    days_until = (instance.scheduled_date - timezone.now().date()).days
    review_link = f'/orders/recurring/instance/{instance.pk}/checkout/'

    # In-app notification (always)
    Notification.objects.create(
        user=user,
        notification_type=Notification.TYPE_ORDER,
        title="Upcoming Recurring Order",
        message=(
            f"Your recurring order is scheduled for "
            f"{instance.scheduled_date.strftime('%A, %d %B %Y')} "
            f"({days_until} day(s) away). Review it before it processes."
        ),
        link=review_link,
    )
    instance.notification_sent = True
    instance.save(update_fields=['notification_sent'])

    # Email (best-effort)
    if user.email:
        try:
            send_mail(
                subject=f"Your weekly order is being prepared — {days_until} days to review",
                message=(
                    f"Hi {user.get_full_name() or user.username},\n\n"
                    f"Your recurring order (#{recurring_order.id}) is scheduled for "
                    f"{instance.scheduled_date.strftime('%A, %d %B %Y')}.\n\n"
                    f"You have {days_until} day(s) to review or modify this order.\n\n"
                    f"Log in at Bristol Regional Food Network to make any changes.\n\n"
                    f"Thank you,\nThe Bristol Regional Food Network Team"
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@brfn.com'),
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send recurring order email: {e}")


def _notify_recurring_producers(recurring_order, instance):
    """Give each relevant producer advance notice without exposing other suppliers."""
    from mainApp.models import Notification

    producer_items = {}
    for item in recurring_order.items.select_related('producer__user'):
        if item.producer and item.producer.user:
            producer_items.setdefault(item.producer, []).append(item.product_name)

    customer_name = recurring_order.customer.get_full_name() or recurring_order.customer.username
    for producer, item_names in producer_items.items():
        Notification.objects.create(
            user=producer.user,
            notification_type=Notification.TYPE_ORDER,
            title='Upcoming Recurring Order',
            message=(
                f'{customer_name} has a recurring order scheduled for '
                f'{instance.scheduled_date:%d %B %Y}: {", ".join(item_names)}. '
                'It will appear in incoming orders after customer confirmation and payment.'
            ),
            link='/notifications/',
        )


# =============================================================================
# TC-019 — Expire surplus deals
# =============================================================================

@shared_task
def expire_surplus_deals():
    """
    Scheduled job: mark SurplusDeals as inactive when:
    - expires_at has passed
    - Product stock_quantity is 0
    - Product availability is not 'available'
    - best_before_date is in the past
    """
    from products.models import SurplusDeal, Product
    from django.utils import timezone
    from datetime import date
    
    now = timezone.now()
    today = now.date()
    count = 0
    
    # Build querysets for each condition
    # 1. expires_at has passed
    q1 = SurplusDeal.objects.filter(is_active=True, expires_at__lte=now)
    
    # 2. Product stock is 0
    q2 = SurplusDeal.objects.filter(is_active=True, product__stock_quantity=0)
    
    # 3. Product is unavailable
    q3 = SurplusDeal.objects.filter(is_active=True, product__availability='unavailable')
    
    # 4. best_before_date is in the past
    q4 = SurplusDeal.objects.filter(is_active=True, best_before_date__lt=today)
    
    # Combine all querysets (union) and get distinct
    to_expire = (q1 | q2 | q3 | q4).distinct().select_related('product')
    
    for deal in to_expire:
        deal.is_active = False
        try:
            deal.full_clean()
            deal.save()
            count += 1
        except ValidationError as e:
            print(f"Failed to expire SurplusDeal {deal.pk}: {e}")
    
    return f"Expired {count} surplus deals"
