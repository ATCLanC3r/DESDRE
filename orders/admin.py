from django.contrib import admin
from .models import OrderPayment, OrderProducer, OrderItem, RecurringOrder, OrderInstance
from mainApp.admin_enforcer import AdminEnforcer
from django.core.exceptions import ValidationError

@admin.register(OrderPayment)
class OrderPaymentAdmin(AdminEnforcer,admin.ModelAdmin):
    list_display = ['id', 'user', 'payment_status', 'total_amount', 'created_at']
    list_filter = ['payment_status', 'created_at']
    search_fields = ['user__username', 'user__email', 'stripe_session_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(OrderProducer)
class OrderProducerAdmin(AdminEnforcer,admin.ModelAdmin):
    list_display = ['id', 'payment', 'producer', 'order_status', 'producer_subtotal', 'is_bulk_order', 'delivered_by']
    list_filter = ['order_status', 'is_bulk_order', 'created_at']
    list_editable = ['order_status']
    search_fields = ['producer__business_name', 'payment__user__username']


@admin.register(RecurringOrder)
class RecurringOrderAdmin(AdminEnforcer,admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'recurrence', 'recurrence_day', 'next_scheduled_date']
    list_filter = ['status', 'recurrence']
    search_fields = ['customer__username']


@admin.register(OrderInstance)
class OrderInstanceAdmin(AdminEnforcer,admin.ModelAdmin):
    list_display = ['id', 'recurring_order', 'scheduled_date', 'status', 'notification_sent']
    list_filter = ['status', 'notification_sent']
    actions = ['mark_confirmed']

    def mark_confirmed(self, request, queryset):
        updated = 0
        for obj in queryset:
            obj.status = 'confirmed'
            try:
                obj.full_clean()
                obj.save()
                updated += 1
            except ValidationError as e:
                self.message_user(request, f"Failed: {e}", level='ERROR')
        self.message_user(request, f"Confirmed {updated} instances.")