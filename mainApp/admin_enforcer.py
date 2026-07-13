from django.contrib import admin
from django.core.exceptions import ValidationError

class AdminEnforcer:
    """Helps with maintaining DB integrity directly from the django built-in admin dashboard"""

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        """Ensure delete goes through proper channels"""
        obj.delete()
    
    def delete_queryset(self, request, queryset):
        """Bulk delete that respects signals"""
        for obj in queryset:
            obj.delete()

    def get_changelist_formset(self, request, **kwargs):
        """
        Ensure bulk edits via list_editable also run model validation.
        """
        formset = super().get_changelist_formset(request, **kwargs)
        
        original_clean = formset.clean
        
        def clean_with_validation(formset_self):
            """
            Clean method that adds model validation.
            """
            original_clean(formset_self)
            
            for form in formset_self.forms:
                if form.has_changed() and hasattr(form, 'instance') and form.instance.pk:
                    try:
                        form.instance.full_clean()
                    except ValidationError as e:
                        # Attach model validation errors to the form
                        if hasattr(e, 'message_dict'):
                            for field, errors in e.message_dict.items():
                                for error in errors:
                                    form.add_error(field, error)
                        else:
                            form.add_error(None, str(e))
        
        formset.clean = clean_with_validation
        return formset

