from django.contrib import admin
from .models import Product, ProductCategory, SurplusDeal
from django.core.exceptions import ValidationError
from mainApp.admin_enforcer import AdminEnforcer

@admin.register(ProductCategory)
class ProductCategoryAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['order', 'name', 'parent', 'is_active', 'product_count']
    list_display_links = ['name']
    list_editable = ['order', 'is_active']

    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    actions = ['activate_categories', 'deactivate_categories']
    
    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'
    
    def activate_categories(self, request, queryset):
        updated=0
        for cateogry in queryset:
            cateogry.is_active = True
            try:
                cateogry.full_clean()
                cateogry.save()
                updated += 1
            except ValidationError as e:
                self.message_user(
                    request,
                    f'Failed to activate {cateogry.name}: {e.message_dict}',
                    level='ERROR'
                )

        self.message_user(request, f'Successfully activated {updated} categories.')
    activate_categories.short_description = "Activate selected categories"
    
    def deactivate_categories(self, request, queryset):
        updated = 0
        for category in queryset:
            category.is_active = False
            try:
                category.full_clean()
                category.save()
                updated += 1
            except ValidationError as e:
                self.message_user(
                    request, 
                    f'Failed to deactivate {category.name}: {e.message_dict}', 
                    level='ERROR'
                )
        self.message_user(request, f'Succesfully deactivated {updated} categories.')
    deactivate_categories.short_description = "Deactivate selected categories"


@admin.register(Product)
class ProductAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'stock_quantity', 'availability', 'is_organic']
    list_filter = ['availability', 'is_organic', 'category', 'created_at']
    list_editable = ['price', 'stock_quantity', 'availability']  # Quick edits
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'category', 'image')
        }),
        ('Pricing & Stock', {
            'fields': ('price', 'unit', 'stock_quantity', 'availability')
        }),
        ('Seasonal & Organic', {
            'fields': ('is_organic', 'season_start', 'season_end', 'harvest_date'),
            'classes': ('collapse',)  # Collapsible section
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SurplusDeal)
class SurplusDealAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['product', 'producer', 'discount_percent', 'discounted_price', 'expires_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    list_editable = ['is_active']
    readonly_fields = ['discounted_price', 'created_at', 'updated_at']
    search_fields = ['product__name', 'producer__business_name']
