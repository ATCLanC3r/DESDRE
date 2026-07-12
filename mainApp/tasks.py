from celery import shared_task
from django.apps import apps
from mainApp.utils import geocode_postcode

@shared_task
def geocode_address_async(address_id):
    try:
        print('running geocoding async')
        Address = apps.get_model('mainApp', 'Address')
        address = Address.objects.get(id=address_id)
        result = address.geocode()
        if result:
            address.save(skip_geocoding=True, skip_default_handling=True)  # Prevent recursion
    except Address.DoesNotExist:
        pass


@shared_task
def send_seasonal_reminders():
    """
    TC-016: Notify producers when one of their products comes into season next month.
    Runs daily via Celery Beat.
    """
    from django.utils import timezone
    from products.models import Product
    from mainApp.models import Notification

    next_month = (timezone.now().month % 12) + 1  # wraps Dec -> Jan

    # Products whose season starts next month, that belong to an active producer
    upcoming = Product.objects.filter(
        is_active=True,
        availability='unavailable',
        season_start=next_month,
        producer__isnull=False,
    ).select_related('producer__user')

    sent = set()
    for product in upcoming:
        producer = product.producer
        if not producer or not producer.user_id:
            continue
        key = (producer.user_id, product.id)
        if key in sent:
            continue
        sent.add(key)

        month_name = dict(Product.MONTH_CHOICES).get(next_month, str(next_month))
        already_notified = Notification.objects.filter(
            user=producer.user,
            notification_type=Notification.TYPE_SYSTEM,
            title="Seasonal Product Reminder",
            message__contains=product.name,
            created_at__month=timezone.now().month,
            created_at__year=timezone.now().year,
        ).exists()

        if already_notified:
            continue

        Notification.objects.create(
            user=producer.user,
            notification_type=Notification.TYPE_SYSTEM,
            title="Seasonal Product Reminder",
            message=(
                f'Your product "{product.name}" comes into season next month ({month_name}). '
                f'Remember to update its availability so customers can order it.'
            ),
            link='/producers/products/',
        )

    return f"Sent seasonal reminders for {len(sent)} product(s)."