from django.db import models
from django.contrib.auth.models import AbstractUser
from mainApp.models import RegularUser
from django.core.exceptions import ValidationError


# =============================================================================
# TC-020 — Producer Recipes & Farm Stories
# =============================================================================
class Season(models.Model):
    '''
    Seasonal tags used by recipe (M2M relationship)
    '''
    name = models.CharField(max_length=20, unique=True)
    slug = models.SlugField(unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order']

    def __str__(self):
        return self.name

    @classmethod #create default fields but seeding already does this
    def get_default_seasons(cls):
        seasons = [
            ('spring', 'Spring', 1),
            ('summer', 'Summer', 2),
            ('autumn', 'Autumn', 3),
            ('winter', 'Winter', 4),
        ]
        for slug, name, order in seasons:
            cls.objects.get_or_create(slug=slug, defaults={'name': name, 'display_order': order})


MODERATION_STATUS_CHOICES = [
    ('pending', 'Pending Review'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]


class Recipe(models.Model):
    """
    A recipe created by a producer, optionally linked to their products.
    Must be approved before appearing publicly.
    """

    producer = models.ForeignKey(
        'mainApp.ProducerProfile',
        on_delete=models.CASCADE,
        related_name='recipes'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    ingredients = models.TextField(help_text="One ingredient per line, or free text")
    instructions = models.TextField(help_text="Step-by-step cooking instructions")
    image = models.ImageField(upload_to='recipes/', null=True, blank=True)

    seasons = models.ManyToManyField(
        'Season',
        blank=True,
        related_name='recipes'
    )

    # Link to products this recipe uses (from the producer's own catalogue)
    linked_products = models.ManyToManyField(
        'products.Product',
        blank=True,
        related_name='recipes'
    )

    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default='pending'
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        if self.is_published and self.moderation_status != 'approved':
            raise ValidationError({
                'is_published': 'Cannot publish a recipe that is not approved.'
            })
        if self.moderation_status == 'rejected':
            self.is_published = False

    def save(self, *args, **kwargs):
        from django.utils import timezone
        if self.is_published and self.moderation_status == 'approved' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class FarmStory(models.Model):
    """
    A farm story / blog post created by a producer.
    Must be approved before appearing publicly.
    """

    producer = models.ForeignKey(
        'mainApp.ProducerProfile',
        on_delete=models.CASCADE,
        related_name='farm_stories'
    )
    title = models.CharField(max_length=255)
    body = models.TextField(help_text="Rich text story body")

    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default='pending'
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Farm stories'

    def __str__(self):
        return self.title

    def clean(self):
        if self.is_published and self.moderation_status != 'approved':
            raise ValidationError({
                'is_published': 'Cannot publish a farm story that is not approved.'
            })
        if self.moderation_status == 'rejected':
            self.is_published = False

    def save(self, *args, **kwargs):
        from django.utils import timezone
        if self.is_published and self.moderation_status == 'approved' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class FarmStoryImage(models.Model):
    """Multiple images for a FarmStory."""

    story = models.ForeignKey(FarmStory, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='farm_stories/')
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']


class SavedRecipe(models.Model):
    """TC-020: Customers can bookmark recipes."""

    customer = models.ForeignKey(
        RegularUser,
        on_delete=models.CASCADE,
        related_name='saved_recipes'
    )
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='saved_by'
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'recipe')
        ordering = ['-saved_at']

    def __str__(self):
        return f"{self.customer.username} saved '{self.recipe.title}'"


# Create your models here.
#class ProducerUser(RegularUser):
#    #is_editor = models.BooleanField(default=False)
#    contact_name = models.CharField('Producer Contact',max_length=50)
#   producer_name = models.CharField('Producer',max_length=50)

# maybe tables for set orders and delivery
#class Post(models.Model):
#    title = models.CharField(max_length=100)
#    content = models.TextField()
#    author = models.ForeignKey(ProducerUser, on_delete=models.CASCADE)
