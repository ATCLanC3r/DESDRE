from django import forms
from mainApp.models import RegularUser
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from mainApp.models import CustomerProfile, Address
import re
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

User = get_user_model()

# =========
# Regular user
# =========
class CustomerLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Remember me",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def confirm_login_allowed(self, user):
        allowed_roles = (User.Role.CUSTOMER, User.Role.COMMUNITY_MEMBER, User.Role.RESTAURANT)
        if user.role not in allowed_roles:
            raise ValidationError(
                "This account is not registered as a customer account.",
                code='invalid_role',
            )
        super().confirm_login_allowed(user)


class UnifiedCustomerRegistrationForm(UserCreationForm):
    """Unified registration form for all customer types (Individual, Community Group, Restaurant)"""

    ROLE_CHOICES = [
        ('customer', 'Individual Customer'),
        ('community_member', 'Community Group/Organisation'),
        ('restaurant', 'Restaurant/Business'),
    ]

    CHARITY_EDUCATION_CHOICES = [
        ('charity', 'Charity'),
        ('education', 'Educational Institution'),
        ('other', 'Other Community Organisation'),
    ]
    
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Choose a username'
        })
    )

    password1 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="New Password",
        help_text="Leave blank to keep your current password."
    )
    password2 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Confirm Password",
    )

    # Role selector
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        label="Account Type"
    )

    # Common fields (all roles)
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        })
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )
    phone_number = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your phone number'
        })
    )

    # Address fields
    address_line1 = forms.CharField(
        required=True,
        label="Address Line 1",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Street address, P.O. Box'
        })
    )
    address_line2 = forms.CharField(
        required=False,
        label="Address Line 2 (optional)",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Apartment, suite, unit, etc.'
        })
    )
    city = forms.CharField(
        required=True,
        initial='Bristol',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'City'
        })
    )
    county = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'County (optional)'
        })
    )
    post_code = forms.CharField(
        required=True,
        label="Post Code",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your post code'
        })
    )

    # Community-specific fields
    organisation_name = forms.CharField(
        required=False,
        label="Organisation Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter organisation name'})
    )
    charity_or_education_status = forms.ChoiceField(
        choices=CHARITY_EDUCATION_CHOICES,
        required=False,
        label="Organisation Type",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    institutional_email = forms.EmailField(
        required=False,
        label="Institutional Email (optional)",
        help_text="Your official organisation email for verification",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter institutional email'})
    )

    # Restaurant-specific fields
    business_name = forms.CharField(
        required=False,
        label="Restaurant / Business Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter business name'})
    )
    business_registration_number = forms.CharField(
        required=False,
        label="VAT / Company Registration Number (optional)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter registration number (optional)'})
    )

    # Terms acceptance
    terms = forms.BooleanField(
        required=True,
        label="I agree to the Terms and Conditions and Privacy Policy",
        error_messages={'required': 'You must accept the Terms and Conditions and Privacy Policy to register.'}
    )

    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'password1', 'password2', 'phone_number',
            'address_line1', 'address_line2', 'city', 'county', 'post_code'
        ]

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email address is already registered. Please use a different email or log in.")
        return email

    def clean_post_code(self):
        post_code = self.cleaned_data.get('post_code')
        uk_postcode_pattern = r'^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$'
        if not re.match(uk_postcode_pattern, post_code.upper()):
            raise ValidationError("Please enter a valid UK postcode.")
        return post_code.upper()

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')

        if role == 'community_member':
            if not cleaned_data.get('organisation_name'):
                self.add_error('organisation_name', 'Organisation name is required for community groups.')
            if not cleaned_data.get('charity_or_education_status'):
                self.add_error('charity_or_education_status', 'Organisation type is required for community groups.')

        elif role == 'restaurant':
            if not cleaned_data.get('business_name'):
                self.add_error('business_name', 'Business name is required for restaurants.')

        return cleaned_data

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.email = self.cleaned_data['email']
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            user.phone_number = self.cleaned_data['phone_number']
            user.role = self.cleaned_data['role']
            user.save()

            # Create address (geocoding will be handled asynchronously by Address.save())
            address_type = 'business' if user.role == 'restaurant' else 'home'
            Address.objects.create(
                user=user,
                address_line1=self.cleaned_data['address_line1'],
                address_line2=self.cleaned_data.get('address_line2', ''),
                city=self.cleaned_data['city'],
                county=self.cleaned_data.get('county', ''),
                post_code=self.cleaned_data['post_code'],
                country='UK',
                address_type=address_type,
                is_default=True,
            )

            # Update role-specific profile fields
            if user.role == 'community_member':
                profile = user.community_member_profile
                profile.organisation_name = self.cleaned_data.get('organisation_name', '')
                profile.charity_or_education_status = self.cleaned_data.get('charity_or_education_status', '')
                profile.institutional_email = self.cleaned_data.get('institutional_email', '')
                profile.save()

            elif user.role == 'restaurant':
                profile = user.restaurant_profile
                profile.business_name = self.cleaned_data.get('business_name', '')
                profile.business_registration_number = self.cleaned_data.get('business_registration_number', '')
                profile.save()

            return user

class CustomerPersonalInfoForm(forms.Form):
    """
    Form for editing customer personal info.
    Addresses are managed separately in the address management section.
    """
    
    # Personal fields only
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'First name', 'class': 'form-control'}))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Last name', 'class': 'form-control'}))
    phone_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Phone number', 'class': 'form-control'}))

    # Password
    password1 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="New Password",
        help_text="Leave blank to keep your current password."
    )
    password2 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Confirm Password",
    )

    # Business fields - for restaurant
    business_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Business name', 'class': 'form-control'}),
        label="Business Name"
    )
    business_registration_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Registration number (optional)', 'class': 'form-control'}),
        label="Business Registration Number"
    )

    # Organisation fields - for community_member
    organisation_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Organisation name', 'class': 'form-control'}),
        label="Organisation Name"
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        # Make all fields optional
        for field in self.fields.values():
            field.required = False

        # Placeholders are set in widget attrs

        # Set initial values based on user role
        if self.user.role == 'restaurant':
            try:
                profile = self.user.restaurant_profile
                self.fields['business_name'].initial = profile.business_name
                self.fields['business_registration_number'].initial = profile.business_registration_number
            except:
                pass
        elif self.user.role == 'community_member':
            try:
                profile = self.user.community_member_profile
                self.fields['organisation_name'].initial = profile.organisation_name
            except:
                pass

    def clean_phone_number(self):
        """Validate phone number format"""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            phone_pattern = r'^[0-9\s\+\-\(\)]{10,}$'
            if not re.match(phone_pattern, phone):
                raise forms.ValidationError("Please enter a valid phone number.")
        return phone

    def clean(self):
        """Validate password fields"""
        cleaned_data = super().clean()
        
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 or password2:
            if not password1:
                self.add_error('password1', "Please enter a new password.")
            elif not password2:
                self.add_error('password2', "Please confirm your password.")
            elif password1 != password2:
                self.add_error('password2', "Passwords do not match.")
            elif len(password1) < 8:
                self.add_error('password1', "Password must be at least 8 characters long.")
            elif password1.isdigit():
                self.add_error('password1', "Password cannot be entirely numeric.")
        
        return cleaned_data

    def save(self, commit=True):
        """Save the form data"""
        user = self.user

        # Update user fields
        user_fields = ["first_name", "last_name", "phone_number"]
        for field in user_fields:
            new_value = self.cleaned_data.get(field)
            if new_value and new_value != getattr(user, field):
                setattr(user, field, new_value)

        # Update profile based on role
        try:
            if user.role == 'restaurant':
                profile = user.restaurant_profile
                business_name = self.cleaned_data.get('business_name')
                if business_name:
                    profile.business_name = business_name
                reg_number = self.cleaned_data.get('business_registration_number')
                if reg_number:
                    profile.business_registration_number = reg_number
                profile.save()

            elif user.role == 'community_member':
                profile = user.community_member_profile
                org_name = self.cleaned_data.get('organisation_name')
                if org_name:
                    profile.organisation_name = org_name
                profile.save()
        except Exception as e:
            print(f"Error saving profile: {e}")

        # Update password if provided
        password1 = self.cleaned_data.get("password1")
        if password1:
            user.set_password(password1)

        if commit:
            # user.full_clean()
            try:
                user.full_clean()
            except ValidationError as e:
                print("Validation errors:", e.message_dict)
            user.save()

        return user
    
     


class CommunityGroupLoginForm(AuthenticationForm):
    """Login form that accepts community_member role users."""
    remember_me = forms.BooleanField(
        required=False,
        label="Remember me (stay logged in for 30 days)",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def confirm_login_allowed(self, user):
        if user.role not in (User.Role.CUSTOMER, User.Role.COMMUNITY_MEMBER):
            raise ValidationError(
                "This account is not registered as a customer or community group.",
                code='invalid_role',
            )
        super().confirm_login_allowed(user)


class RestaurantLoginForm(AuthenticationForm):
    """Login form for restaurant accounts."""
    remember_me = forms.BooleanField(
        required=False,
        label="Remember me (stay logged in for 30 days)",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def confirm_login_allowed(self, user):
        if user.role != User.Role.RESTAURANT:
            raise ValidationError(
                "This account is not registered as a restaurant.",
                code='invalid_role',
            )
        super().confirm_login_allowed(user)