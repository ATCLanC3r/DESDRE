from celery import shared_task
from django.core.files.storage import default_storage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task
def refresh_demo_image_urls():
    """
    Periodic task: Scan Backblaze bucket for demo images in demo/products/
    and update Product.demo_image_url field.
    """
    if not (settings.DEBUG or getattr(settings, 'USE_DEMO_IMAGES', False)):
        return "Demo images not enabled. Skipping."

    from products.models import Product
    
    updated = 0
    errors = 0
    
    # 1. List all files in demo/products/
    try:
        if not hasattr(default_storage, 'listdir'):
            return "Storage backend does not support listdir."
            
        # Assuming structure: demo/products/{product_id}.ext
        dirs, files = default_storage.listdir('demo/products')
        
        # Build a map: {product_id: filename}
        # Example: "123.jpg" -> 123
        demo_map = {}
        valid_ext = ['jpg', 'jpeg', 'png', 'webp']
        
        for f in files:
            parts = f.split('.')
            if len(parts) == 2 and parts[1].lower() in valid_ext:
                try:
                    pid = int(parts[0])  # filename is product ID
                    demo_map[pid] = f
                except ValueError:
                    continue # not a numeric ID
        
        # 2. Get products that need updating
        products_to_update = Product.objects.filter(
            demo_image_url=''  # No cached URL yet
        )
        
        # 3. Update products found in bucket
        for product in products_to_update:
            if product.id in demo_map:
                key = f"demo/products/{demo_map[product.id]}"
                try:
                    url = default_storage.url(key)
                    product.demo_image_url = url
                    product.save(update_fields=['demo_image_url'])
                    updated += 1
                except Exception as e:
                    logger.warning(f"Failed to get URL for {key}: {e}")
                    errors += 1
        
        # # 4. Clear demo_image_url for products that no longer have demo images
        # products_with_stale_url = Product.objects.filter(
        #     demo_image_url__gt='',
        #     image=''
        # )
        
        # for product in products_with_stale_url:
        #     # Check if the URL still exists
        #     if product.demo_image_url:
        #         try:
        #             # Just verify it starts with our demo path
        #             if 'demo/products/' not in product.demo_image_url:
        #                 continue
                    
        #             # Try to get the key from URL
        #             # This is expensive, so we just skip for now
        #             # In future, could implement stale URL cleanup
        #         except Exception:
        #             pass
        
        return f"Updated {updated} demo image URLs. Errors: {errors}."
    
    except Exception as e:
        return f"Task failed: {e}"