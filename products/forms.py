from django.db import models
from products.models import Product, ProductCategory
from django.utils import timezone
from django import forms
from products.models import Allergen, Product, SurplusDeal
from django.forms import CheckboxInput #
import os

ALLOWED_MB_IMAGE = 5 # this will be used for the allowed image size to accept

# ===============
# add/edit product validation
# ===============
class ProductForm(forms.ModelForm):
    """
    Form for producers to add/edit products (TC-003)
    """

    allergen_list = forms.ModelMultipleChoiceField(
        queryset=Allergen.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'allergen-checkbox'}),
        required=False,
        label="Allergens",
        help_text="Select all allergens present in this product"
    )

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'price', 'unit',
            'stock_quantity', 'low_stock_threshold', 'availability', 'is_organic',
            'season_start', 'season_end', 'harvest_date', 'image',
            'allergen_list', 'allergen_statement',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Detailed product description...'}),
            'harvest_date': forms.DateInput(attrs={'type': 'date'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'stock_quantity': forms.NumberInput(attrs={'min': '0'}),
            'allergen_statement': forms.Textarea(attrs={
                'rows': 2,
                "placeholder": 'E.g., "May contain traces of nuts due to shared equipment"',
                'class': 'form-control'
            }),
        }
        help_texts = {
            'season_start': 'Leave blank if available year-round',
            'season_end': 'Leave blank if available year-round',
            'unit': 'e.g., kg, dozen, 500g, each',
            'allergen_statement': 'Optional: Add any additional allergen warnings'
        }

    def __init__(self, *args, **kwargs):
        self.producer = kwargs.pop('producer', None)
        super().__init__(*args, **kwargs)
        
        # Filter categories to only show active ones
        self.fields['category'].queryset = ProductCategory.objects.filter(is_active=True)
        
        # Make some fields optional
        self.fields['season_start'].required = False
        self.fields['season_end'].required = False
        self.fields['harvest_date'].required = False
        self.fields['image'].required = False
        self.fields['allergen_list'].required = False
        self.fields['allergen_statement'].required = False
        self.fields['low_stock_threshold'].required = False
        
        # Add CSS classes
        for field in self.fields:
            if field not in ['allergen_list', 'is_organic']:
                self.fields[field].widget.attrs.update({'class': 'form-control'})

        if self.instance and self.instance.pk:
            self.fields['allergen_list'].initial = self.instance.allergens.all()

    def clean(self):
        """Custom validation"""
        cleaned_data = super().clean()
        season_start = cleaned_data.get('season_start')
        season_end = cleaned_data.get('season_end')
        allergen_list = cleaned_data.get('allergen_list')
        allergen_statement = cleaned_data.get('allergen_statement')
        
        # If one season field is set, both should be set
        if (season_start and not season_end) or (not season_start and season_end):
            raise forms.ValidationError(
                "Both season start and end must be set together, or leave both blank for year-round availability."
            )
        
        # Validate season range
        if season_start and season_end:
            if season_start > season_end:
                # Check if it's a winter season (Dec-Jan)
                if not (season_start == 12 and season_end == 1):
                    raise forms.ValidationError(
                        "Season end must be after season start, except for winter seasons (Dec-Jan)."
                    )
                
        if allergen_list and not allergen_statement:
            # Not required, but we might want to encourage it
            cleaned_data['allergen_statement'] = f"Contains: {', '.join([a.get_name_display() for a in allergen_list])}"
        
        return cleaned_data
    
    def clean_image(self):
        image = self.cleaned_data.get('image')

        if not image:
            return image
        
        if image.size > ALLOWED_MB_IMAGE * 1024 * 1024:
            raise forms.ValidationError(f"Image file too large (max {ALLOWED_MB_IMAGE}MB)")
        
        return image
    
    def clean_price(self):
        price = self.cleaned_data.get('price')

        if price <= 0:
            raise forms.ValidationError(f"Price must be greater than 0.")
        
        return price
    
    def clean_stock_quantity(self):
        stock_quantity = self.cleaned_data.get('stock_quantity')

        if stock_quantity < 0:
            raise forms.ValidationError(f"Stock quantity must be greater than 0.")
        
        return stock_quantity
    
    def clean_harvest_date(self):
        """Validate that harvest_date is not in the future."""     
        harvest_date = self.cleaned_data.get('harvest_date')

        # If no date provided, that's okay (field is optional)
        if not harvest_date:
            return harvest_date
        
        # harvest date cannot be in the future.
        today = timezone.now().date()
        if harvest_date > today:
            raise forms.ValidationError("Best before date cannot be in the future.")
        
        return harvest_date

    def save(self, commit=True):
        product = super().save(commit=False)
        
        # Set the producer
        if self.producer:
            product.producer = self.producer

        # Fall back to model default if threshold left blank
        if not product.low_stock_threshold:
            product.low_stock_threshold = 10
        
        # Auto-set availability based on season if not manually set
        if not product.availability and product.season_start and product.season_end:
            current_month = timezone.now().month
            if product.season_start <= current_month <= product.season_end:
                product.availability = 'in_season'
            else:
                product.availability = 'out_of_season'
        
        allergen_list = self.cleaned_data.get('allergen_list')
        product.has_allergens = bool(allergen_list and allergen_list.exists())

        if commit:
            product.full_clean()
            product.save()

            # Set many-to-many allergens
            if allergen_list:
                product.allergens.set(allergen_list)
            else:
                product.allergens.clear()

            # Auto generate allergen notes
            if allergen_list:
                names = [a.get_name_display() for a in allergen_list]

                if len(names) > 3:
                    product.allergen_notes = f"Contains: {', '.join(names[:3])} and others"
                else:
                    product.allergen_notes = f"Contains: {', '.join(names)}"

            else:
                product.allergen_notes = "No common allergens"

            product.save(update_fields=['allergen_notes', 'has_allergens'])

        return product


# ===============
# Surplus form 
# ===============
class SurplusDealForm(forms.ModelForm):
    """
    Form for creating/updating SurplusDeal with proper validation.
    Addresses integrity.md issue: validates product availability and stock.
    """
    expires_hours = forms.IntegerField(
        min_value=1,
        initial=48,
        help_text="Hours until this deal expires",
        widget=forms.NumberInput(attrs={'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm'})
    )
    
    class Meta:
        model = SurplusDeal
        fields = ['discount_percent', 'note', 'best_before_date']
        widgets = {
            'discount_percent': forms.NumberInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm',
                'min': '10',
                'max': '50'
            }),
            'note': forms.Textarea(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none',
                'rows': 2,
                'placeholder': 'e.g. "Perfect condition, must sell quickly"'
            }),
            'best_before_date': forms.DateInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm',
                'type': 'date'
            }),
        }
        help_texts = {
            'discount_percent': 'Discount between 10% and 50%',
            'best_before_date': 'Optional: when the product best before date',
        }
    
    def __init__(self, *args, **kwargs):
        self.product = kwargs.pop('product', None)
        super().__init__(*args, **kwargs)
    
    def clean_discount_percent(self):
        discount = self.cleaned_data['discount_percent']
        if discount < 10:
            raise forms.ValidationError("Discount must be at least 10%.")
        if discount > 50:
            raise forms.ValidationError("Discount cannot exceed 50%.")
        return discount
    
    def clean_best_before_date(self):
        """Validate that best_before_date is not in the past."""     
        best_before_date = self.cleaned_data.get('best_before_date')

        # If no date provided, that's okay (field is optional)
        if not best_before_date:
            return best_before_date
        
        # Check that date is not in the past (must be today or future)
        today = timezone.now().date()
        if best_before_date < today:
            raise forms.ValidationError("Best before date cannot be in the past.")
        
        return best_before_date
    
    def clean(self):
        cleaned_data = super().clean()
        
        if self.product:
            # Check product is available
            if self.product.availability != 'available':
                raise forms.ValidationError(
                    "Cannot create surplus deal for unavailable product. "
                    f"Current status: {self.product.get_availability_display()}"
                )
            
            # Check stock quantity
            if self.product.stock_quantity <= 0:
                raise forms.ValidationError(
                    "Cannot create surplus deal for out-of-stock product. "
                    f"Current stock: {self.product.stock_quantity}"
                )
            
            # Set original_price from product
            self.instance.original_price = self.product.price
            self.instance.product = self.product
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if self.product:
            instance.product = self.product
            instance.original_price = self.product.price
        
        if commit:
            instance.full_clean()  # Explicit validation
            instance.save()
        
        return instance
