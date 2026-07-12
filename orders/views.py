from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from mainApp.decorators import customer_required, restaurant_required, producer_required, community_member_required
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import stripe
from datetime import date, timedelta, datetime
from customers.models import Cart
from mainApp.models import Address
from orders.models import (
    OrderPayment, OrderProducer, OrderItem,
    RecurringOrder, RecurringOrderItem, OrderInstance, OrderInstanceItem,
)
from decimal import ROUND_HALF_UP
from django.contrib.auth import get_user_model
from django.utils import timezone
import json
import uuid
from django.db import transaction
from django.db import models


User = get_user_model()


def next_recurrence_date(weekday_name, start=None):
    """Return the next occurrence after today for a stored weekday name."""
    weekdays = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    start = start or timezone.localdate()
    target = weekdays.get(weekday_name, 0)
    days_ahead = (target - start.weekday()) % 7 or 7
    return start + timedelta(days=days_ahead)


@customer_required
def checkout(request):

    try:
        cart = request.user.cart
    except (AttributeError, Cart.DoesNotExist):
        return redirect('mainApp:products:product_list')

    if cart.items.count() == 0:
        return redirect('mainApp:products:product_list')

    addresses = request.user.addresses.all()
    default_address = addresses.filter(
        address_type='shipping', is_default=True
        ).first() or addresses.filter(is_default=True).first()

    if not default_address and addresses.exists():
        # Edge case: addresses exist but none is default — promote the first one
        default_address = addresses.order_by('-created_at').first()
        default_address.is_default = True
        default_address.save()

    # Calculate totals
    total = cart.total_amount()
    commission_total = (total * Decimal('0.05')).quantize(Decimal('0.01'))

    producer_groups = cart.get_items_by_producer()

    now = timezone.now()
    for group in producer_groups.values():
        min_delivery = now + timedelta(hours=group['lead_time_hours'])
        group['min_delivery_date'] = min_delivery.date().isoformat()
        group['min_delivery_display'] = min_delivery.strftime('%d %b %Y')

    context = {
        'cart': cart,
        'cart_items': cart.items.select_related('product').all(),
        'total': total,
        'addresses': addresses,
        'default_address': default_address,
        'commission_total': commission_total,
        'producer_total': total - commission_total,
        'min_delivery_date': (date.today() + timedelta(days=2)).strftime('%Y-%m-%d'),
        'producer_groups': producer_groups,
    }

    return render(request, "orders/checkout.html", context)



def _valid_test_card(number):
    """Basic Luhn validation; this simulated gateway never sends or stores card data."""
    if not number.isdigit() or not 12 <= len(number) <= 19:
        return False
    digits = [int(value) for value in number]
    parity = len(digits) % 2
    total = 0
    for index, value in enumerate(digits):
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


@customer_required
@require_POST
def create_simulated_checkout_session(request):
    """Process an assessment-safe simulated payment and create the order atomically."""
    card_number = ''.join(ch for ch in request.POST.get('card_number', '') if ch.isdigit())
    cardholder = request.POST.get('cardholder_name', '').strip()
    expiry = request.POST.get('card_expiry', '').strip()
    cvc = request.POST.get('card_cvc', '').strip()

    payment_errors = []
    if not cardholder:
        payment_errors.append('Enter the test cardholder name.')
    if not _valid_test_card(card_number):
        payment_errors.append('Enter a valid test card number.')
    try:
        expiry_month, expiry_year = (int(part) for part in expiry.split('/', 1))
        expiry_year += 2000 if expiry_year < 100 else 0
        if not 1 <= expiry_month <= 12 or (expiry_year, expiry_month) < (date.today().year, date.today().month):
            raise ValueError
    except (TypeError, ValueError):
        payment_errors.append('Enter a future expiry date in MM/YY format.')
    if not cvc.isdigit() or len(cvc) not in (3, 4):
        payment_errors.append('Enter a valid test CVC.')
    if card_number == '4000000000000002':
        payment_errors.append('The simulated payment was declined. Use test card 4242 4242 4242 4242.')
    if payment_errors:
        for error in payment_errors:
            messages.error(request, error)
        return redirect('mainApp:orders:checkout')

    try:
        cart = request.user.cart
    except (AttributeError, Cart.DoesNotExist):
        messages.error(request, 'Cart not found.')
        return redirect('mainApp:orders:checkout')
    producer_groups = cart.get_items_by_producer()
    if not producer_groups:
        messages.error(request, 'Your cart is empty.')
        return redirect('mainApp:orders:checkout')

    try:
        address = Address.objects.get(id=request.POST.get('address_id'), user=request.user)
    except (Address.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Please select a valid delivery address.')
        return redirect('mainApp:orders:checkout')

    now = timezone.now()
    delivery_dates = {}
    for producer_id, group in producer_groups.items():
        try:
            delivery_date = datetime.strptime(
                request.POST.get(f'delivery_date_{producer_id}', ''), '%Y-%m-%d'
            ).date()
        except ValueError:
            messages.error(request, f"Select a valid delivery date for {group['business_name']}.")
            return redirect('mainApp:orders:checkout')
        if delivery_date < (now + timedelta(hours=group['lead_time_hours'])).date():
            messages.error(request, f"{group['business_name']} requires at least {group['lead_time_hours']} hours notice.")
            return redirect('mainApp:orders:checkout')
        delivery_dates[producer_id] = delivery_date

        for cart_item in group['items']:
            if not cart_item.product or cart_item.product.stock_quantity < cart_item.quantity:
                messages.error(request, f'Insufficient stock for {cart_item.product_name}.')
                return redirect('mainApp:orders:checkout')

    # The documented decline card fails before this point, so failed attempts create no order.
    reference = f"SIM-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"
    is_bulk = getattr(request.user, 'role', '') == 'community_member'
    with transaction.atomic():
        payment = OrderPayment.objects.create(
            user=request.user,
            total_amount=cart.total_amount(),
            shipping_address_id=address,
            global_delivery_notes=request.POST.get('global_delivery_notes', ''),
            special_instructions=request.POST.get('special_instructions', ''),
            payment_status='paid',
            payment_reference=reference,
            payment_method='simulated_card',
            masked_payment_details=f"Test card ending {card_number[-4:]}",
        )
        for producer_id, group in producer_groups.items():
            producer_order = OrderProducer.objects.create(
                payment=payment,
                producer=group['producer'],
                producer_subtotal=group['subtotal'],
                order_status='pending',
                customer_note=request.POST.get(f'customer_note_{producer_id}', ''),
                delivered_by=delivery_dates[producer_id],
                is_bulk_order=is_bulk,
            )
            for cart_item in group['items']:
                OrderItem.objects.create(
                    producer_order=producer_order,
                    product=cart_item.product,
                    product_name=cart_item.product_name,
                    product_price=cart_item.unit_price,
                    quantity=cart_item.quantity,
                    unit=cart_item.product.unit,
                )
                cart_item.product.deduct_stock(cart_item.quantity)
            try:
                from mainApp.models import Notification
                Notification.objects.create(
                    user=producer_order.producer.user,
                    notification_type=Notification.TYPE_ORDER,
                    title='New Order Received',
                    message=f'New order #{payment.id} is awaiting confirmation.',
                    link=reverse('mainApp:producers:incoming_orders'),
                )
            except Exception:
                pass
        cart.clear_cart()

    return redirect(reverse('mainApp:orders:success') + f'?reference={reference}')


@customer_required
def create_checkout_session(request):
    """Create Stripe Checkout Session"""

    if request.method != 'POST':
        return redirect('mainApp:orders:checkout')

    # Configure the Stripe SDK with the secret key. Without this the SDK has no
    # api_key and stripe.checkout.Session.create() raises an AuthenticationError
    # (a StripeError), which the handler below silently converts into a redirect
    # back to checkout -- so the customer can never reach the Stripe payment page.
    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PUBLISHABLE_KEY:
        messages.error(request, 'Stripe Test Mode is not configured. Add both Stripe test API keys and restart the application.')
        return redirect('mainApp:orders:checkout')

    cart = request.user.cart
    now  = timezone.now()
    address_id = request.POST.get('address_id')
    global_delivery_notes = request.POST.get('global_delivery_notes', '')
    special_instructions = request.POST.get('special_instructions', '')  # TC-017

    producer_groups = cart.get_items_by_producer()

    # Validate delivery date per producer
    delivery_dates = {}   # { producer_id: date }
    errors = []

    for producer_id, group in producer_groups.items():
        date_str = request.POST.get(f'delivery_date_{producer_id}')
        if not date_str:
            errors.append(f"Please select a delivery date for {group['business_name']}.")
            continue

        try:
            delivery_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            errors.append(f"Invalid delivery date for {group['business_name']}.")
            continue

        lead_hours = group['lead_time_hours']
        min_delivery = (now + timedelta(hours=lead_hours)).date()

        if delivery_date < min_delivery:
            errors.append(
                f"{group['business_name']} requires at least {lead_hours}h notice. "
                f"Earliest available date is {min_delivery.strftime('%d %b %Y')}."
            )
            continue

        delivery_dates[producer_id] = delivery_date

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect('mainApp:orders:checkout')

    # Validate address
    try:
        address = Address.objects.get(id=address_id, user=request.user)
    except Address.DoesNotExist:
        messages.error(request, 'Please select a valid address')
        return redirect('mainApp:orders:checkout')

    # Get cart
    try:
        cart = request.user.cart
    except (AttributeError, Cart.DoesNotExist):
        messages.error(request, 'Cart not found')
        return redirect('mainApp:orders:checkout')

    if cart.items.count() == 0:
        messages.error(request, 'Cart is empty')
        return redirect('mainApp:orders:checkout')

    # Re-check stock for all cart items before creating a Stripe session
    from products.models import Product as ProductModel
    stock_errors = []
    for cart_item in cart.items.select_related('product').all():
        if cart_item.product is None:
            continue
        # Re-fetch current stock from DB to catch concurrent changes
        current_stock = ProductModel.objects.filter(id=cart_item.product.id).values_list('stock_quantity', flat=True).first()
        if current_stock is None or cart_item.quantity > current_stock:
            stock_errors.append(
                f'"{cart_item.product_name}" only has {current_stock or 0} units in stock but you requested {cart_item.quantity}.'
            )
    if stock_errors:
        for err in stock_errors:
            messages.error(request, err)
        return redirect('mainApp:orders:checkout')

    # Build line items for Stripe
    line_items = []
    for cart_item in cart.items.select_related('product').all():
        price_in_cents = int(cart_item.unit_price * 100)
        line_items.append({
            'price_data': {
                'currency': 'gbp',
                'product_data': {
                    'name': cart_item.product.name,
                    'description': cart_item.product.description[:100] if cart_item.product.description else "",
                },
                'unit_amount': price_in_cents,
            },
            'quantity': cart_item.quantity,
        })

    use_mock = False
    if use_mock:
        mock_session_id = f"mock_{timezone.now().strftime('%Y%m%d%H%M%S')}_{request.user.id}"
        
        # TC-017: detect community group accounts for bulk order flagging
        is_community_group = (
            hasattr(request.user, 'role') and
            request.user.role == 'community_member'
        )

        # TC-018: recurring order for restaurant users
        make_recurring = request.POST.get('make_recurring') == 'on'
        recurrence = request.POST.get('recurrence', 'weekly')
        recurrence_day = request.POST.get('recurrence_day', 'monday')
        delivery_day = request.POST.get('delivery_day', 'monday')

        with transaction.atomic():
            # Create OrderPayment (customer payment)
            payment = OrderPayment.objects.create(
                user=request.user,
                stripe_session_id=mock_session_id,
                total_amount=cart.total_amount(),  # Just product total
                shipping_address_id=address,
                global_delivery_notes=global_delivery_notes,
                special_instructions=special_instructions,  # TC-017
                payment_status='paid' # Set to paid immediately in mock mode
            )

            # Create OrderProducer for each producer
            for producer_id, group in producer_groups.items():
                delivery_date = delivery_dates.get(producer_id)
                customer_note = request.POST.get(f'customer_note_{producer_id}', '')

                order_producer = OrderProducer.objects.create(
                    payment=payment,
                    producer=group['producer'],
                    producer_subtotal=group['subtotal'],
                    order_status='confirmed', # Set to confirmed immediately
                    customer_note=customer_note,
                    delivered_by=delivery_date,
                    is_bulk_order=is_community_group,  # TC-017
                )

                for cart_item in group['items']:
                    OrderItem.objects.create(
                        producer_order=order_producer,
                        product=cart_item.product,
                        product_name=cart_item.product.name,
                        product_price=cart_item.unit_price,
                        quantity=cart_item.quantity,
                        unit=cart_item.product.unit,
                    )

                    # Deduct stock and track surplus deal
                    if cart_item.product:
                        cart_item.product.deduct_stock(cart_item.quantity)
                        try:
                            deal = cart_item.product.surplus_deal
                            if deal and deal.is_active:
                                deal.record_sale(cart_item.quantity)
                        except Exception:
                            pass

                # Notify producer
                try:
                    from mainApp.models import Notification
                    producer_user = order_producer.producer.user
                    item_count = order_producer.order_items.count()
                    Notification.objects.create(
                        user=producer_user,
                        notification_type=Notification.TYPE_ORDER,
                        title="New Order Received",
                        message=(
                            f"You have a new order from {payment.user.get_full_name() or payment.user.username} "
                            f"({item_count} item{'s' if item_count != 1 else ''}, "
                            f"£{order_producer.producer_subtotal:.2f})."
                        ),
                        link=reverse('mainApp:producers:incoming_orders'),
                    )
                except Exception as e:
                    print(f"Failed to create producer notification: {e}")

            # TC-018: create RecurringOrder for restaurant users who opted in
            if make_recurring and hasattr(request.user, 'role') and request.user.role == 'restaurant':
                from orders.models import RecurringOrder, RecurringOrderItem
                recurring = RecurringOrder.objects.create(
                    customer=request.user,
                    status='active',
                    recurrence=recurrence,
                    recurrence_day=recurrence_day,
                    delivery_day=delivery_day,
                    delivery_address=address,
                    delivery_notes=global_delivery_notes,
                    next_scheduled_date=next_recurrence_date(recurrence_day),
                )
                for cart_item in cart.items.select_related('product').all():
                    RecurringOrderItem.objects.create(
                        recurring_order=recurring,
                        product=cart_item.product,
                        producer=cart_item.product.producer if cart_item.product else None,
                        product_name=cart_item.product.name if cart_item.product else cart_item.product_name,
                        quantity=cart_item.quantity,
                        unit=cart_item.product.unit if cart_item.product else '',
                    )

            # Clear cart
            try:
                request.user.cart.clear_cart()
            except Exception:
                pass

        return redirect(reverse('mainApp:orders:success') + f'?session_id={mock_session_id}')

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,  # Just the products
            mode='payment',
            success_url=request.build_absolute_uri(reverse('mainApp:orders:success')) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri(reverse('mainApp:orders:cancel')),
            customer_email=request.user.email,
            metadata={
                # Stripe requires all metadata values to be strings; cast every
                # value so a None phone number (or int id) can't raise an error.
                'user_id': str(request.user.id),
                'user_name': request.user.get_full_name() or '',
                'user_email': request.user.email or '',
                'user_phone_number': str(request.user.phone_number or ''),
                'address_id': str(address.id),
                'global_delivery_notes': global_delivery_notes or '',
                'cart_id': str(request.user.cart.id),
                'item_count': str(cart.item_count()),
                'item_total': str(cart.total_amount()),
                'total_producers_involved': str(len(producer_groups)),
                # 'delivery_dates': json.dumps({
                #     str(pid): d.isoformat()
                #     for pid, d in delivery_dates.items()
                # }),
            }
        )
        # TC-017: detect community group accounts for bulk order flagging
        is_community_group = (
            hasattr(request.user, 'role') and
            request.user.role == 'community_member'
        )

        # TC-018: recurring order for restaurant users
        make_recurring = request.POST.get('make_recurring') == 'on'
        recurrence = request.POST.get('recurrence', 'weekly')
        recurrence_day = request.POST.get('recurrence_day', 'monday')
        delivery_day = request.POST.get('delivery_day', 'monday')

        with transaction.atomic():
            # Create OrderPayment (customer payment)
            payment = OrderPayment.objects.create(
                # customer=request.user.customer_profile,
                user=request.user,
                stripe_session_id=checkout_session.id,
                total_amount=cart.total_amount(),  # Just product total
                shipping_address_id=address,  # save() fills shipping_address text from this
                global_delivery_notes=global_delivery_notes,
                special_instructions=special_instructions,  # TC-017
                payment_status='pending'
            )

            # Create OrderProducer for each producer (commission calculated here)
            producer_groups = cart.get_items_by_producer()
            for producer_id, group in producer_groups.items():
                delivery_date = delivery_dates.get(producer_id)
                customer_note = request.POST.get(f'customer_note_{producer_id}', '')

                producer_order = OrderProducer.objects.create(
                    payment=payment,
                    producer=group['producer'],
                    producer_subtotal=group['subtotal'],  # What customer paid for these items
                    order_status='pending',
                    customer_note=customer_note,
                    delivered_by=delivery_date,
                    is_bulk_order=is_community_group,  # TC-017
                )

                for cart_item in group['items']:
                    OrderItem.objects.create(
                        producer_order=producer_order,
                        product=cart_item.product,
                        product_name=cart_item.product.name,
                        product_price=cart_item.unit_price,
                        quantity=cart_item.quantity,
                        unit=cart_item.product.unit,
                    )

            # TC-018: create RecurringOrder for restaurant users who opted in
            if make_recurring and hasattr(request.user, 'role') and request.user.role == 'restaurant':
                from orders.models import RecurringOrder, RecurringOrderItem
                recurring = RecurringOrder.objects.create(
                    customer=request.user,
                    status='active',
                    recurrence=recurrence,
                    recurrence_day=recurrence_day,
                    delivery_day=delivery_day,
                    delivery_address=address,
                    delivery_notes=global_delivery_notes,
                    next_scheduled_date=next_recurrence_date(recurrence_day),
                )
                for cart_item in cart.items.select_related('product').all():
                    RecurringOrderItem.objects.create(
                        recurring_order=recurring,
                        product=cart_item.product,
                        producer=cart_item.product.producer if cart_item.product else None,
                        product_name=cart_item.product.name if cart_item.product else cart_item.product_name,
                        quantity=cart_item.quantity,
                        unit=cart_item.product.unit if cart_item.product else '',
                    )

        return redirect(checkout_session.url)

    except stripe.error.StripeError as e:
        messages.error(request, str(e))
        return redirect('mainApp:orders:checkout')

@customer_required
def success(request):
    """Handle successful payment."""
    session_id = request.GET.get('session_id')
    reference = request.GET.get('reference')
    lookup = models.Q(stripe_session_id=session_id) if session_id else models.Q(payment_reference=reference)
    order = OrderPayment.objects.filter(lookup, user=request.user).first()

    # A browser redirect is not proof of payment. Verify the Checkout Session
    # with Stripe before changing financial or fulfilment state. The signed
    # webhook performs the same transition if the customer closes this page.
    if order and order.payment_status == 'pending' and session_id:
        try:
            if not settings.STRIPE_SECRET_KEY:
                raise RuntimeError('Stripe is not configured.')
            stripe.api_key = settings.STRIPE_SECRET_KEY
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            if checkout_session.payment_status != 'paid':
                messages.warning(request, 'Stripe has not confirmed this payment yet.')
                return render(request, 'orders/success.html', {'order': order})
            order.stripe_payment_intent_id = checkout_session.payment_intent
        except (stripe.error.StripeError, RuntimeError) as exc:
            messages.error(request, f'Unable to verify payment: {exc}')
            return render(request, 'orders/success.html', {'order': order})

    if order and order.payment_status == 'pending':
        with transaction.atomic():
            # Get order producers using correct related_name
            order_producers = order.producer_orders.all()

            if order_producers:
                for order_producer in order_producers:
                    order_producer.order_status = "confirmed"
                    order_producer.save()
                    # Notify the producer about the new order
                    try:
                        from mainApp.models import Notification
                        producer_user = order_producer.producer.user
                        item_count = order_producer.order_items.count()
                        Notification.objects.create(
                            user=producer_user,
                            notification_type=Notification.TYPE_ORDER,
                            title="New Order Received",
                            message=(
                                f"You have a new order from {order.user.get_full_name() or order.user.username} "
                                f"({item_count} item{'s' if item_count != 1 else ''}, "
                                f"£{order_producer.producer_subtotal:.2f})."
                            ),
                            link=reverse('mainApp:producers:incoming_orders'),
                        )
                    except Exception as e:
                        print(f"Failed to create producer notification: {e}")

            # Deduct stock from ORDER ITEMS
            for order_producer in order_producers:
                for item in order_producer.order_items.all():
                    if item.product:
                        item.product.deduct_stock(item.quantity)
                        # TC-019: track units sold under a surplus deal
                        try:
                            deal = item.product.surplus_deal
                            if deal and deal.is_active:
                                deal.record_sale(item.quantity)
                        except Exception:
                            pass

            # Mark payment as paid
            order.payment_status = 'paid'
            order.save()

    try:
        request.user.cart.clear_cart()
    except Exception:
        pass

    return render(request, 'orders/success.html', {'order': order})

@customer_required
def cancel(request):
    """Handle cancelled payment"""
    return render(request, 'orders/cancel.html')

@csrf_exempt
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    # print("webhook received")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        existing_payment = OrderPayment.objects.filter(stripe_session_id=session['id']).first()

        # If already paid (webhook fired twice), do nothing
        if existing_payment and existing_payment.payment_status == 'paid':
            return HttpResponse(status=200)

        try:
            if existing_payment:
                # Order was pre-created at checkout; confirm it and finalise
                payment = existing_payment
            else:
                # This should NEVER happen - create_checkout_session pre-creates the payment
                raise Exception(
                    f"Payment not found for Stripe session: {session['id']}. "
                    "Checkout session may have failed to create payment records."
                )

            # Get order producers using correct related_name
            order_producers = payment.producer_orders.all()

            if order_producers:
                for order_producer in order_producers:
                    order_producer.order_status="confirmed"
                    order_producer.save()
                    # Notify the producer about the new order
                    try:
                        from mainApp.models import Notification
                        from django.urls import reverse
                        producer_user = order_producer.producer.user
                        item_count = order_producer.order_items.count()
                        Notification.objects.create(
                            user=producer_user,
                            notification_type=Notification.TYPE_ORDER,
                            title="New Order Received",
                            message=(
                                f"You have a new order from {payment.user.get_full_name() or payment.user.username} "
                                f"({item_count} item{'s' if item_count != 1 else ''}, "
                                f"£{order_producer.producer_subtotal:.2f})."
                            ),
                            link=reverse('mainApp:producers:incoming_orders'),
                        )
                    except Exception as e:
                        print(f"Failed to create producer notification: {e}")

            # Deduct stock from ORDER ITEMS (not cart items)
            # this elimate a very far edge case of user maybe adding item to the cart while paying
            # which will deduct the item even if the user didn't order it
            for order_producer in order_producers:
                for item in order_producer.order_items.all():
                    if item.product:
                        item.product.deduct_stock(item.quantity)
                        # TC-019: track units sold under a surplus deal
                        try:
                            deal = item.product.surplus_deal
                            if deal and deal.is_active:
                                deal.record_sale(item.quantity)
                        except Exception:
                            pass

            # Clear cart after successful stock deduction
            # assume cart has only ordered items
            try:
                if hasattr(payment.user, 'cart'):
                    payment.user.cart.clear_cart()
            except (AttributeError, Cart.DoesNotExist):
                pass  # Cart already cleared or doesn't exist

            # mark payment as paid
            payment.stripe_payment_intent_id = session.get('payment_intent')
            payment.payment_status = 'paid'
            payment.save()

        except Exception as e:
            print(f"Webhook order processing failed: {e}")
            return HttpResponse(status=500)
    return HttpResponse(status=200)


# =========
# profile
# =========

def get_time_group(created_at):
    """Group orders by time period"""
    now = timezone.now()
    if created_at >= now - timedelta(days=7):
        return 'This Week'
    elif created_at >= now - timedelta(days=30):
        return 'This Month'
    else:
        return 'Earlier'


def get_overall_status(producer_orders):
    """
    Option B: Strict logic - filter by overall status
    - All delivered = completed
    - Any cancelled = cancelled
    - All confirmed/preparing/ready = active
    """
    statuses = [po.order_status for po in producer_orders]

    if not statuses:
        return 'active'

    if all(s == 'delivered' for s in statuses):
        return 'completed'
    if 'cancelled' in statuses:
        return 'cancelled'
    return 'active'


@login_required
def order_history(request):
    '''
    Universal order history page
    '''
    if request.user.role == User.Role.PRODUCER:
        return redirect('mainApp:producers:incoming_orders')

    orders = OrderPayment.objects.exclude(
        payment_status__in=['pending', 'failed']
    )
    if not (request.user.is_staff or request.user.role == User.Role.SYSTEM_ADMIN):
        if request.user.role not in (
            User.Role.CUSTOMER,
            User.Role.COMMUNITY_MEMBER,
            User.Role.RESTAURANT,
        ):
            messages.error(request, 'You do not have permission to view orders.')
            return redirect('mainApp:home')
        orders = orders.filter(user=request.user)
    orders = orders.order_by('-created_at', '-id')

    orders_data = []

    for order in orders:
        # Get all producer orders for this payment
        producer_orders = list(order.producer_orders.select_related(
            'producer'
        ).prefetch_related(
            'order_items__product'
        ).all())

        # Build comprehensive order data
        order_info = {
            'order': order,
            'total_amount': order.total_amount,
            'created_at': order.created_at,
            'payment_status': order.payment_status,
            'payment_status_display': order.get_payment_status_display(),
            'shipping_address': order.shipping_address,
            'global_notes': order.global_delivery_notes,
            'time_group': get_time_group(order.created_at),
            'overall_status': get_overall_status(producer_orders),
            'producers': []
        }

        for producer_order in producer_orders:
            producer_data = {
                'producer': producer_order.producer,
                'business_name': producer_order.producer.business_name if producer_order.producer else 'Unknown',
                'status': producer_order.order_status,
                'status_display': producer_order.get_order_status_display(),
                'subtotal': producer_order.producer_subtotal,
                'delivery_date': producer_order.delivered_by,
                'completed_at': producer_order.completed_at,
                'customer_note': producer_order.customer_note,
                'items': []
            }

            # Get items for this producer order
            for item in producer_order.order_items.all():
                producer_data['items'].append({
                    'id': item.id,
                    'product_id': item.product.id if item.product else None,
                    'name': item.product_name,
                    'quantity': item.quantity,
                    'price': item.product_price,
                    'line_total': item.line_total,
                    'unit': item.unit
                })

            order_info['producers'].append(producer_data)

        # Add delivered_date for completed orders
        if get_overall_status(producer_orders) == 'completed':
            delivered_dates = [po.completed_at for po in producer_orders if po.completed_at]
            if delivered_dates:
                order_info['delivered_date'] = max(delivered_dates).strftime('%d %b %Y')

        orders_data.append(order_info)

    # Count active orders (any producer active)
    active_orders = sum(1 for od in orders_data if od['overall_status'] == 'active')

    context = {
        'orders': orders,
        'orders_data': orders_data,
        'total_orders': orders.count(),
        'active_orders': active_orders,
    }

    return render(request, "orders/profile/order_history.html", context)


@login_required
def reorder(request, order_id):
    """Add all items from a past order back into the current cart."""
    from customers.models import CartItem
    from django.contrib import messages

    order = get_object_or_404(OrderPayment, id=order_id, user=request.user)
    cart, _ = Cart.objects.get_or_create(user=request.user)

    added, unavailable = [], []
    for producer_order in order.producer_orders.prefetch_related('order_items__product'):
        for item in producer_order.order_items.all():
            product = item.product
            if product and product.availability == 'available' and product.stock_quantity > 0 and product.is_active:
                cart_item, created = CartItem.objects.get_or_create(
                    cart=cart, product=product,
                    defaults={'quantity': item.quantity}
                )
                if not created:
                    cart_item.quantity += item.quantity
                    cart_item.save(update_fields=['quantity'])
                added.append(item.product_name)
            else:
                unavailable.append(item.product_name)

    if added:
        messages.success(request, f"{len(added)} item(s) added to your cart.")
    if unavailable:
        messages.warning(request, f"{len(unavailable)} item(s) are no longer available: {', '.join(unavailable)}.")

    return redirect('mainApp:customers:view_cart')


# =============================================================================
# TC-018 — Recurring Orders (restaurant accounts)
# =============================================================================

@restaurant_required
def recurring_orders_list(request):
    """List all recurring orders for the logged-in restaurant/customer."""
    recurring_orders = RecurringOrder.objects.filter(
        customer=request.user
    ).prefetch_related('items__product', 'instances').order_by('-created_at')

    context = {
        'recurring_orders': recurring_orders,
    }
    return render(request, 'orders/recurring/list.html', context)


@restaurant_required
def recurring_order_detail(request, pk):
    """View and manage a single recurring order."""
    recurring_order = get_object_or_404(RecurringOrder, pk=pk, customer=request.user)
    instances = recurring_order.instances.order_by('-scheduled_date')[:10]

    context = {
        'recurring_order': recurring_order,
        'instances': instances,
    }
    return render(request, 'orders/recurring/detail.html', context)


@restaurant_required
@require_POST
def pause_recurring_order(request, pk):
    """Pause an active recurring order."""
    if request.method != 'POST':
        return redirect('mainApp:orders:recurring_list')
    recurring_order = get_object_or_404(RecurringOrder, pk=pk, customer=request.user)
    if recurring_order.status == 'active':
        recurring_order.status = 'paused'
        recurring_order.save(update_fields=['status'])
    return redirect('mainApp:orders:recurring_list')


@restaurant_required
def resume_recurring_order(request, pk):
    """Resume a paused recurring order."""
    if request.method != 'POST':
        return redirect('mainApp:orders:recurring_list')
    recurring_order = get_object_or_404(RecurringOrder, pk=pk, customer=request.user)
    if recurring_order.status == 'paused':
        recurring_order.status = 'active'
        recurring_order.save(update_fields=['status'])
    return redirect('mainApp:orders:recurring_list')


@restaurant_required
def cancel_recurring_order(request, pk):
    """Cancel a recurring order."""
    if request.method != 'POST':
        return redirect('mainApp:orders:recurring_list')
    recurring_order = get_object_or_404(RecurringOrder, pk=pk, customer=request.user)
    recurring_order.status = 'cancelled'
    recurring_order.save(update_fields=['status'])
    return redirect('mainApp:orders:recurring_list')


@restaurant_required
def edit_instance(request, pk):
    """Edit the next pending instance of a recurring order (quantities only)."""
    instance = get_object_or_404(
        OrderInstance, pk=pk,
        recurring_order__customer=request.user,
        status__in=['pending', 'confirmed']
    )

    if request.method == 'POST':
        with transaction.atomic():
            instance.items.all().delete()
            items_count = int(request.POST.get('items_count', 0))
            for i in range(items_count):
                product_id = request.POST.get(f'product_{i}')
                quantity = request.POST.get(f'quantity_{i}', 1)
                item = instance.recurring_order.items.filter(product_id=product_id).first()
                if item and int(quantity) > 0:
                    OrderInstanceItem.objects.create(
                        instance=instance,
                        product=item.product,
                        product_name=item.product_name,
                        quantity=int(quantity),
                        unit=item.unit,
                    )
            instance.status = 'modified'
            instance.save(update_fields=['status'])
        return redirect('mainApp:orders:recurring_detail', pk=instance.recurring_order_id)

    context = {'instance': instance}
    return render(request, 'orders/recurring/edit_instance.html', context)


@restaurant_required
def checkout_instance(request, pk):
    """
    TC-018: Load a recurring order instance into the cart and redirect to checkout.
    Skips items that are no longer available and warns the user.
    """
    from customers.models import CartItem

    instance = get_object_or_404(
        OrderInstance, pk=pk, recurring_order__customer=request.user
    )

    cart = request.user.cart
    cart.clear_cart()

    added, skipped = [], []
    for item in instance.items.select_related('product'):
        product = item.product
        if product and product.availability == 'available' and product.is_active and product.stock_quantity > 0:
            CartItem.objects.create(
                cart=cart,
                product=product,
                product_name=product.name,
                unit_price=product.price,
                quantity=item.quantity,
            )
            added.append(product.name)
        else:
            skipped.append(item.product_name)

    if skipped:
        from django.contrib import messages as dj_messages
        dj_messages.warning(
            request,
            f"Some items were unavailable and skipped: {', '.join(skipped)}."
        )

    instance.status = 'confirmed'
    instance.save(update_fields=['status'])

    return redirect('mainApp:orders:checkout')


# =============================================================================
# TC-021 — Order receipt download (PDF)
# =============================================================================

@login_required
def download_order_receipt(request, order_id):
    """Generate and return a PDF receipt for a paid customer order."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    import io

    order = get_object_or_404(OrderPayment, id=order_id, user=request.user)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER, spaceAfter=4)
    sub_style = ParagraphStyle('sub', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.grey, spaceAfter=12)
    label_style = ParagraphStyle('label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)
    value_style = ParagraphStyle('value', parent=styles['Normal'], fontSize=9)
    right_style = ParagraphStyle('right', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=9)

    elements = []
    elements.append(Paragraph("Bristol Regional Food Network", title_style))
    elements.append(Paragraph("Order Receipt", sub_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#d1fae5')))
    elements.append(Spacer(1, 6 * mm))

    # Order metadata
    meta = [
        [Paragraph("Order #", label_style), Paragraph(str(order.id), value_style)],
        [Paragraph("Date", label_style), Paragraph(order.created_at.strftime("%d %B %Y"), value_style)],
        [Paragraph("Status", label_style), Paragraph(order.get_payment_status_display(), value_style)],
        [Paragraph("Delivery address", label_style), Paragraph(order.shipping_address or "—", value_style)],
    ]
    meta_table = Table(meta, colWidths=[45 * mm, 120 * mm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 6 * mm))

    # Line items per producer
    for producer_order in order.producer_orders.prefetch_related('order_items').all():
        producer_name = producer_order.producer.business_name if producer_order.producer else "Unknown Producer"
        elements.append(Paragraph(producer_name, styles['Heading3']))

        rows = [["Item", "Qty", "Unit", "Price", "Total"]]
        for item in producer_order.order_items.all():
            rows.append([
                item.product_name,
                str(item.quantity),
                item.unit,
                f"£{item.product_price:.2f}",
                f"£{item.line_total:.2f}",
            ])
        rows.append(["", "", "", Paragraph("Subtotal", label_style), f"£{producer_order.producer_subtotal:.2f}"])

        item_table = Table(rows, colWidths=[70 * mm, 15 * mm, 20 * mm, 25 * mm, 25 * mm])
        item_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#065f46')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f0fdf4')]),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#d1d5db')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(item_table)
        elements.append(Spacer(1, 4 * mm))

    # Grand total row
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    total_table = Table(
        [["", Paragraph("Grand Total", label_style), Paragraph(f"£{order.total_amount:.2f}", label_style)]],
        colWidths=[100 * mm, 40 * mm, 25 * mm],
    )
    total_table.setStyle(TableStyle([('ALIGN', (1, 0), (-1, -1), 'RIGHT'), ('TOPPADDING', (0, 0), (-1, -1), 4)]))
    elements.append(total_table)
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("Thank you for supporting local producers!", sub_style))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_order_{order.id}.pdf"'
    return response
