from django.db import models
from django.utils import timezone
from django.template.defaultfilters import slugify
from products.utility import product_image_path
from django.db import transaction

class Product(models.Model):
    '''
    Product model for marketplace

    allergen statement is handled in forum.
    '''
    # Definitions
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    AVAILABILITY_CHOICES = [
    # ('in_season', 'In Season'),
    ('available', 'Available'),
    # ('out_of_season', 'Out of Season'),
    ('unavailable', 'Unavailable'),
    ]

    UNIT_CHOICES = [
        ('kg', 'Kilogram (kg)'),
        ('g', 'Gram (g)'),
        ('lb', 'Pound (lb)'),
        ('oz', 'Ounce (oz)'),
        ('ml', 'Millilitres (ml)'),
        ('litre', 'Litre (L)'),
        ('dozen', 'Dozen'),
        ('half dozen', 'Half Dozen'),
        ('each', 'Each'),
        ('bunch', 'Bunch'),
        ('500g', '500 grams'),
        ('250g', '250 grams'),
        ('1kg', '1 kilogram'),
        ('jar', 'Jar'),
        ('pack', 'Pack'),
        ('bottle', 'Bottle'),
        ('pair', 'Pair'),
        ('piece', 'Piece'),
    ]

    # Table information
    name=models.CharField(max_length=100, help_text="Product name") # maybe create this null= false
    description = models.TextField(help_text="Detailed product description")
    price = models.DecimalField(max_digits=8, decimal_places=2, help_text="Price per unit") # same with this
    unit = models.CharField(max_length=50, choices=UNIT_CHOICES, help_text="e.g., kg, dozen, each")
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Current stock level")

    slug = models.SlugField(unique=True, blank=True)

    producer = models.ForeignKey(
        'mainApp.ProducerProfile',
        on_delete=models.PROTECT,
        related_name='products',
        null=True,
        blank=True,
    )

    availability = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default='available',
        help_text='is this product available for purchase?'
    )


    harvest_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_organic = models.BooleanField(default=False)

    season_start = models.IntegerField(choices=MONTH_CHOICES, null=True, blank=True)
    season_end = models.IntegerField(choices=MONTH_CHOICES, null=True, blank=True)

    # media
    image = models.ImageField(upload_to=product_image_path,null=True,blank=True, help_text="Product image")
    demo_image_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Auto-detected demo image URL from bucket (set by Celery task)"
    )

    category = models.ForeignKey(
        'ProductCategory',
        on_delete=models.SET_NULL,
        null=True,
        related_name='products',
        help_text='Product category'
    )

    # Allergen information
    allergens = models.ManyToManyField(
        "Allergen",
        blank=True,
        related_name='products',
        help_text="Select all allergens present in this product"
    )
    allergen_statement = models.TextField(
        blank=True,
        help_text="Additional allergen information or preparation notes (e.g., 'May contain traces of nuts due to shared equipment')"
    )
    has_allergens= models.BooleanField(default=False,help_text="Does this product contain any allergens?")
    allergen_notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Brief allergen warning for quick display")


    # handle soft delete fields
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="False if product has been soft deleted (hidden from store but kept for historical orders)"
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        help_text="Timestamp when product was soft deleted"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "product"
        verbose_name_plural = "products"

        # unique_together = ['name', 'producer']

        ordering = ['category', 'name']

        # allow quicker queries
        indexes = [
            models.Index(fields=['name'])
        ]

        # check contraints of fields
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name='price_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name='stock_non_negative'
            ),
        ]

    def deduct_stock(self, quantity):
        from django.db.models import F
        old_stock = self.stock_quantity
        updated = Product.objects.filter(
            pk=self.pk,
            stock_quantity__gte=quantity
        ).update(stock_quantity=F('stock_quantity') - quantity)
        if updated:
            self.refresh_from_db(fields=['stock_quantity'])
            # Notify producer only when stock crosses the threshold downward
            if old_stock > self.low_stock_threshold and self.is_low_stock and self.producer:
                self._send_low_stock_notification()
            return True
        return False
        #with transaction.atomic():
        #    product = Product.objects.filter(
        #        pk=self.pk,
        #    ).first()

        #    if product:
        #        product.stock_quantity -= quantity
        #        product.full_clean()  # Explicit validation
        #        product.save(update_fields=['stock_quantity'])
        #        self.stock_quantity = product.stock_quantity
        #        return True
        #
        #    return False

    def _send_low_stock_notification(self):
        try:
            from mainApp.models import Notification
            from django.urls import reverse
            Notification.objects.create(
                user=self.producer.user,
                notification_type=Notification.TYPE_SYSTEM,
                title="Low Stock Alert",
                message=(
                    f'"{self.name}" is running low — '
                    f'{self.stock_quantity} {self.unit} remaining '
                    f'(alert threshold: {self.low_stock_threshold}).'
                ),
                link=reverse('mainApp:producers:myproduct'),
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to send low stock notification for product {self.pk}"
            )

    def save(self, *args, **kwargs):
        try:
            # Check if this is an existing product being updated
            if self.pk:
                old_product = Product.objects.get(pk=self.pk)

                # If there was an old image and it's different from the new one
                if old_product.image and old_product.image != self.image:
                    old_product.image.delete(save=False)
        except Product.DoesNotExist:
            pass

        if not self.slug:
            self.slug = slugify(self.name)
            original_slug = self.slug
            counter = 1
            while Product.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1

        # auto availability
        if self.stock_quantity == 0:
            self.availability="unavailable"
        # If stock > 0, don't auto-change availability - producer controls this

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        force = kwargs.pop('force', False)
        if force:
            self.hard_delete()
        else:
            self.soft_delete()

    def soft_delete(self):
        """Soft delete the product - hides from store but keeps for order history"""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.availability = 'unavailable'
        self.save(update_fields=['is_active', 'deleted_at', 'availability'])

    def hard_delete(self):
        """Permanently delete the product (use with caution!)"""
        if self.image:
            self.image.delete(save=False)
        super().delete()

    @property
    def is_in_season(self):
        """
        Check if product is currently in season based on season_start and season_end.
        Returns True if:
        - No season dates set (always in season)
        - Current month falls within season range
        """
        if not (self.season_start and self.season_end):
            return True  # No season restriction = always in season

        current_month = timezone.now().month

        if self.season_start <= self.season_end:
            return self.season_start <= current_month <= self.season_end
        else:
            return current_month >= self.season_start or current_month <= self.season_end

    @property
    def is_available(self):
        """
        Combined availability: product must be both available AND in season
        This is what should be shown to customers
        """
        return (
            self.is_active
            and self.availability == 'available'
            and self.stock_quantity > 0
            and self.is_in_season
        )

    def get_season_display(self):
        """
        Returns formatted season dates like 'June - August' or 'October - March'.
        Returns 'Year-round' if no season dates set.
        """
        if not (self.season_start and self.season_end):
            return 'Year-round'

        month_names = dict(Product.MONTH_CHOICES)
        start_month = month_names.get(self.season_start, '')
        end_month = month_names.get(self.season_end, '')

        return f"{start_month} - {end_month}"

    low_stock_threshold = models.PositiveIntegerField(
        default=10,
        help_text="Show a low-stock warning when stock falls at or below this level"
    )

    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def has_deal(self):
        return hasattr(self, 'surplus_deal') and self.surplus_deal is not None

    @property
    def image_url(self):
        # 1. Uploaded image (fastest, DB check)
        if self.image:
            return self.image.url

        # 2. Cached demo image URL from Celery task (DB check, NO API CALL)
        if self.demo_image_url:
            return self.demo_image_url

        return None

    def get_food_miles(self, user_lat, user_long):
        """
        TC-013: Distance in miles from the producer's farm to Bristol city centre.
        Returns None if the producer has no geocoded location.
        """
        from mainApp.utils import haversine_miles, BRISTOL_LAT, BRISTOL_LON
        producer = self.producer
        if not producer or not producer.latitude or not producer.longitude:
            return None

        if user_lat is not None and user_long is not None:
            lat, lon = user_lat, user_long
        else:
            lat, lon = BRISTOL_LAT, BRISTOL_LON

        return round(haversine_miles(producer.latitude, producer.longitude, lat, lon), 2)

    @property
    def allergen_display(self):
        if not self.has_allergens:
            return "No common allergens"

        allergen_list = self.allergens.all()
        if not allergen_list:
            return "No common allergens"

        return f"Contatins: {', '.join([a.get_name_display() for a in allergen_list])}"

# =============================================================================
# Product category
# =============================================================================

class ProductCategory(models.Model):
    '''
    Product categories
    '''

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    slug = models.SlugField(unique=True) # for urls path
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)

    order = models.PositiveIntegerField(default=0) # can be used to rank the ranking of the categories.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "product category"
        verbose_name_plural = "product categories"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    ### Functions
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) # set url path to use the name of the category
        super().save(*args, **kwargs)


# =============================================================================
# TC-019 — Surplus / Last-Minute Deals
# =============================================================================

class SurplusDeal(models.Model):
    """
    A time-limited discount applied to a product to reduce food waste.
    Created by producers; expires automatically via a scheduled job.
    """

    product = models.OneToOneField(
        'Product',
        on_delete=models.CASCADE,
        related_name='surplus_deal'
    )
    producer = models.ForeignKey(
        'mainApp.ProducerProfile',
        on_delete=models.CASCADE,
        related_name='surplus_deals'
    )

    discount_percent = models.PositiveIntegerField(
        help_text="Discount between 10 and 50 percent inclusive"
    )
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2)

    note = models.CharField(
        max_length=500,
        blank=True,
        help_text="e.g. 'Perfect condition, must sell quickly'"
    )
    best_before_date = models.DateField(null=True, blank=True)
    expires_at = models.DateTimeField(help_text="When this deal automatically expires")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(discount_percent__gte=10),
                name='surplus_discount_min'
            )
        ]

    def save(self, *args, **kwargs):
        from decimal import Decimal
        if not self.discounted_price: # edge case if discounted price wasn't calculated when clean is called.
            self.discounted_price = (
                self.original_price * (1 - Decimal(self.discount_percent) / 100)
            ).quantize(Decimal('0.01'))

        super().save(*args, **kwargs)

    def clean(self):
        """Pre-calculate discounted_price before validation."""
        from decimal import Decimal
        from django.core.exceptions import ValidationError

        errors = {}
        if self.discount_percent is not None and not 10 <= self.discount_percent <= 50:
            errors['discount_percent'] = 'Discount must be between 10% and 50%.'
        if self.expires_at and self.expires_at <= timezone.now():
            errors['expires_at'] = 'Expiry must be in the future.'
        if errors:
            raise ValidationError(errors)

        # Only calculate if we have the required fields
        if self.original_price is not None and self.discount_percent is not None:
            self.discounted_price = (
                self.original_price * (1 - Decimal(self.discount_percent) / 100)
            ).quantize(Decimal('0.01'))

        super().clean()

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    # TC-019 analytics: track how many units sold under the deal
    units_sold = models.PositiveIntegerField(default=0, help_text="Units sold at the discounted price")

    def record_sale(self, quantity: int):
        """Increment units_sold atomically when a surplus item is purchased."""
        from django.db.models import F
        SurplusDeal.objects.filter(pk=self.pk).update(units_sold=F('units_sold') + quantity)

    def __str__(self):
        return f"{self.discount_percent}% off {self.product.name} (expires {self.expires_at:%d %b %Y %H:%M})"


class Allergen(models.Model):
    """
    TC-015 & TC-03 allergen information
    """
    ALLERGEN_CHOICES = [
        ('celery', 'Celery'),
        ('cereals_gluten', 'Cereals containing gluten (wheat, rye, barley, oats)'),
        ('crustaceans', 'Crustaceans (prawns, crabs, lobster)'),
        ('eggs', 'Eggs'),
        ('fish', 'Fish'),
        ('lupin', 'Lupin'),
        ('milk', 'Milk'),
        ('molluscs', 'Molluscs (mussels, oysters, snails)'),
        ('mustard', 'Mustard'),
        ('nuts', 'Nuts (almonds, hazelnuts, walnuts, etc.)'),
        ('peanuts', 'Peanuts'),
        ('sesame', 'Sesame seeds'),
        ('soya', 'Soya'),
        ('sulphites', 'Sulphur dioxide / sulphites'),
    ]

    name = models.CharField(max_length=50, choices=ALLERGEN_CHOICES, unique=True)
    display_name = models.CharField(max_length=100, help_text="Display name for the allergen")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name

    class Meta:
        ordering = ['name']
        verbose_name = "allergen"
        verbose_name_plural = "allergens"

    def get_name_display(self):
        return self.display_name

class ProductReview(models.Model):
    """TC-024: Customer reviews for purchased products."""

    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    customer = models.ForeignKey(
        'mainApp.RegularUser',
        on_delete=models.CASCADE,
        related_name='product_reviews',
    )
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['product', 'customer']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating}★ {self.product.name} by {self.customer.username}"



class ProducerReviewResponse(models.Model):
    """TC-024: A producer's public reply to a customer review."""
    review = models.OneToOneField(
        'ProductReview',
        on_delete=models.CASCADE,
        related_name='producer_response',
    )
    producer = models.ForeignKey(
        'mainApp.ProducerProfile',
        on_delete=models.CASCADE,
        related_name='review_responses',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Response to review #{self.review_id} by {self.producer.business_name}"


    # user class should have a one to one extension
    # - helps maintain 1 unique username and email per user
    # - a producer can be a buyer and vice versa
