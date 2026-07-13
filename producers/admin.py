from django.contrib import admin
from .models import Recipe, FarmStory, FarmStoryImage, SavedRecipe, Season
from mainApp.admin_enforcer import AdminEnforcer


class FarmStoryImageInline(AdminEnforcer, admin.TabularInline):
    model = FarmStoryImage
    extra = 0


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'display_order']
    list_editable = ['display_order']
    search_fields = ['name']


@admin.register(Recipe)
class RecipeAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['title', 'producer', 'moderation_status', 'is_published', 'created_at']
    list_filter = ['moderation_status', 'is_published', 'seasons', 'created_at']
    search_fields = ['title', 'producer__business_name']
    filter_horizontal = ['linked_products', 'seasons']
    readonly_fields = ['created_at', 'updated_at', 'published_at']
    actions = ['approve_and_publish', 'reject_and_unpublish', 'mark_pending']

    def approve_and_publish(self, request, queryset):
        for recipe in queryset:
            recipe.moderation_status = 'approved'
            recipe.is_published = True
            recipe.full_clean()
            recipe.save()
        self.message_user(request, f"Approved and published {queryset.count()} recipes.")
    approve_and_publish.short_description = "Approve and publish selected recipes"

    def reject_and_unpublish(self, request, queryset):
        for story in queryset:
            story.moderation_status = 'rejected'
            story.is_published = False
            story.full_clean()
            story.save()
        self.message_user(request, f"Rejected and unpublished {queryset.count()} recipes.")
    reject_and_unpublish.short_description = "Reject and unpublish selected recipes"

    def mark_pending(self, request, queryset):
        for recipe in queryset:
            recipe.moderation_status = 'pending'
            recipe.is_published = False
            recipe.full_clean()
            recipe.save()
        self.message_user(request, f"Marked {queryset.count()} recipes as pending.")
    mark_pending.short_description = "Mark selected recipes as pending"


@admin.register(FarmStory)
class FarmStoryAdmin(AdminEnforcer, admin.ModelAdmin):
    list_display = ['title', 'producer', 'moderation_status', 'is_published', 'created_at']
    list_filter = ['moderation_status', 'is_published', 'created_at']
    search_fields = ['title', 'producer__business_name']
    readonly_fields = ['created_at', 'updated_at', 'published_at']
    inlines = [FarmStoryImageInline]
    actions = ['approve_and_publish', 'reject_and_unpublish', 'mark_pending']

    def approve_and_publish(self, request, queryset):
        for story in queryset:
            story.moderation_status = 'approved'
            story.is_published = True
            story.full_clean()
            story.save()
        self.message_user(request, f"Approved and published {queryset.count()} farm stories.")
    approve_and_publish.short_description = "Approve and publish selected farm stories"

    def reject_and_unpublish(self, request, queryset):
        for story in queryset:
            story.moderation_status = 'rejected'
            story.is_published = False
            story.full_clean()
            story.save()
        self.message_user(request, f"Rejected and unpublished {queryset.count()} farm stories.")
    reject_and_unpublish.short_description = "Reject and unpublish selected farm stories"

    def mark_pending(self, request, queryset):
        for story in queryset:
            story.moderation_status = 'pending'
            story.is_published = False
            story.full_clean()
            story.save()
        self.message_user(request, f"Marked {queryset.count()} farm stories as pending.")
    mark_pending.short_description = "Mark selected farm stories as pending"


@admin.register(SavedRecipe)
class SavedRecipeAdmin(AdminEnforcer,   admin.ModelAdmin):
    list_display = ['customer', 'recipe', 'saved_at']
    list_filter = ['saved_at']
    search_fields = ['customer__username', 'recipe__title']
