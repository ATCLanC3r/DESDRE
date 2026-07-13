from django.contrib import admin
from .models import (
    RegularUser, Address, CustomerProfile, ProducerProfile,
    CommunityMemberProfile, RestaurantProfile, SystemAdminProfile,
    Notification,
)
from mainApp.admin_enforcer import AdminEnforcer
from django.core.exceptions import ValidationError


@admin.register(RegularUser)
class RegularUserAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']


@admin.register(CommunityMemberProfile)
class CommunityMemberProfileAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['user', 'organisation_name', 'charity_or_education_status', 'is_verified']
    list_filter = ['charity_or_education_status', 'is_verified']
    search_fields = ['organisation_name', 'user__username', 'user__email']

    actions = ['verify_selected']
    def verify_selected(self, request, queryset):
        updated = 0
        for obj in queryset:
            obj.is_verified = True
            try:
                obj.full_clean()
                obj.save()
                updated += 1
            except ValidationError as e:
                self.message_user(request, f"Failed: {e}", level='ERROR')
        self.message_user(request, f"Verified {updated} profiles.")


@admin.register(RestaurantProfile)
class RestaurantProfileAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['business_name', 'user', 'business_registration_number', 'is_verified']
    list_filter = ['is_verified']
    list_editable = ['is_verified']
    search_fields = ['business_name', 'user__username']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['user__username', 'title', 'message']
    list_editable = ['is_read']
    date_hierarchy = 'created_at'
