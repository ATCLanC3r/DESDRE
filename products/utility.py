import os
from uuid import uuid4
from django.utils import timezone
from django.conf import settings

# ===============
# Product Bucket
# ===============
def product_image_path(instance, filename):
    '''
    generate file path for product image
    '''
    extension = filename.split('.')[-1].lower()

    product_id =instance.id
    if settings.USE_DEMO_IMAGES:
        dev_prefix = "demo"
    else:
        dev_prefix = getattr(settings, 'DEV_NAME', "demo")

    return f"{dev_prefix}/products/{product_id}.{extension}"
