from django.db import models
# from django.conf import settings
from decimal import Decimal
from uuid import uuid4
from mainApp.models import CustomerProfile, RegularUser


def generate_order_number():
    '''
    DEPRECATED
    '''
    return uuid4().hex[:12].upper()


class Cart(models.Model):
    user = models.OneToOneField(RegularUser, on_delete=models.CASCADE, related_name="cart")
    updated_at = models.DateTimeField(auto_now=True)

    # @property
    def total_amount(self):
        '''
        Returns total amount fo the cart.
        '''
        # user only pay the total amount of items (NO COMISSION)
        total = sum((item.line_total for item in self.items.all()), Decimal("0.00"))
        return total
    
    def subtotal(self):
        subtotal = sum((item.line_total for item in self.items.all()), Decimal("0.00"))
        return round(subtotal,2)
    
    def item_count(self):
        return sum(item.quantity for item in self.items.all())
    
    def get_items_by_producer(self):
        """
        Group cart items by producer.
        Commission is calculated at payout time, not at checkout.
        """
        groups = {}
        for item in self.items.select_related('product__producer').all():
            producer = item.product.producer
            if not producer:
                continue
                
            if producer.id not in groups:
                groups[producer.id] = {
                    'producer': producer,
                    'business_name': producer.business_name,
                    'items': [],
                    'subtotal': Decimal('0.00'),
                    'lead_time_hours': getattr(producer, 'lead_time_hours', 48),
                }
            groups[producer.id]['items'].append(item)
            groups[producer.id]['subtotal'] += item.line_total
        
        return groups
    
    def get_producer_summary(self):
        """
        Get a summary of producers in cart (without full item details)
        Useful for checkout page
        """
        groups = self.get_items_by_producer()
        summary = []
        for producer_id, data in groups.items():
            summary.append({
                'producer_id': producer_id,
                'business_name': data['business_name'],
                'item_count': len(data['items']),
                'total_quantity': sum(item.quantity for item in data['items']),
                'subtotal': data['subtotal'],
                'lead_time_hours': data['lead_time_hours'],
            })
        return summary
    
    def clear_cart(self):
        self.items.all().delete()

    def __str__(self):
        return f"Cart({self.user})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="cart_items",
        null=True,
        blank=True
    )  
    product_name= models.CharField(max_length=255, blank=True) #snapshot of the product
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def line_total(self):
        price = self.unit_price if self.unit_price is not None else Decimal(0.00)
        return price * self.quantity
    
    def save(self, *args, **kwargs):
        "populate snapshots if not available"

        if self.product:
            if not self.product_name:
                self.product_name = self.product.name
            if self.unit_price is None:
                try:
                    from django.utils import timezone as tz
                    deal = self.product.surplus_deal
                    if deal.is_active and deal.expires_at > tz.now():
                        self.unit_price = deal.discounted_price
                    else:
                        self.unit_price = self.product.price
                except Exception:
                    self.unit_price = self.product.price
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.quantity} x {self.product_name}"
