from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


def customer_required(view_func):
    """Decorator to require customer role for access (customer, community_member, restaurant)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check authentication
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect('mainApp:customers:login')
        
        # Check role - accepts all customer-side roles
        allowed_roles = (
            request.user.Role.CUSTOMER,
            request.user.Role.COMMUNITY_MEMBER,
            request.user.Role.RESTAURANT,
        )
        if request.user.role not in allowed_roles:
            messages.error(request, 'You need a customer account to access this page.')
            return redirect("mainApp:home")
        
        # Check profile exists based on role
        if request.user.role == request.user.Role.CUSTOMER:
            if not hasattr(request.user, 'customer_profile'):
                messages.error(request, 'Your customer profile is not set up correctly.')
                return redirect("mainApp:home")
        elif request.user.role == request.user.Role.COMMUNITY_MEMBER:
            if not hasattr(request.user, 'community_member_profile'):
                messages.error(request, 'Your community member profile is not set up correctly.')
                return redirect("mainApp:home")
        elif request.user.role == request.user.Role.RESTAURANT:
            if not hasattr(request.user, 'restaurant_profile'):
                messages.error(request, 'Your restaurant profile is not set up correctly.')
                return redirect("mainApp:home")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def producer_required(view_func):
    """Decorator to require producer role for access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect('mainApp:producers:login')
        
        if request.user.role != request.user.Role.PRODUCER:
            messages.error(request, 'You need a producer account to access this page.')
            return redirect("mainApp:home")
        
        if not hasattr(request.user, 'producer_profile'):
            messages.error(request, 'Your producer profile is not set up correctly.')
            return redirect("mainApp:home")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def community_member_required(view_func):
    """Decorator to require community member role for access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect('mainApp:customers:community_login')
        
        if request.user.role != request.user.Role.COMMUNITY_MEMBER:
            messages.error(request, 'You need a community member account to access this page.')
            return redirect("mainApp:home")
        
        if not hasattr(request.user, 'community_member_profile'):
            messages.error(request, 'Your community member profile is not set up correctly.')
            return redirect("mainApp:home")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def restaurant_required(view_func):
    """Decorator to require restaurant role for access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect('mainApp:customers:restaurant_login')
        
        if request.user.role != request.user.Role.RESTAURANT:
            messages.error(request, 'You need a restaurant account to access this page.')
            return redirect("mainApp:home")
        
        if not hasattr(request.user, 'restaurant_profile'):
            messages.error(request, 'Your restaurant profile is not set up correctly.')
            return redirect("mainApp:home")
        
        return view_func(request, *args, **kwargs)
    return wrapper

