#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
    if ! python manage.py shell -c "from products.models import Product; raise SystemExit(0 if Product.objects.exists() else 1)"; then
        echo "Creating demonstration accounts and marketplace data..."
        python manage.py seed_producers
        python manage.py seed_customers
        python manage.py seed_allergens
        python manage.py seed_products2
        python manage.py seed_seasons
        python manage.py seed_recipes_stories
        python manage.py seed_admins
    else
        echo "Demo data already exists; skipping seed commands."
    fi
fi

exec "$@"

