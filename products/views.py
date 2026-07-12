from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Product, ProductCategory, ProductReview, Allergen
from django.db.models import Case, When, Value, BooleanField, Q, F
from django.contrib.postgres.search import TrigramSimilarity
from mainApp.utils import haversine_miles, BRISTOL_LAT, BRISTOL_LON
from mainApp.decorators import producer_required, customer_required
from producers.models import Recipe, Season, FarmStory, SavedRecipe
from django.db.models import IntegerField

from django.utils import timezone

def product_list(request):
    '''
    Display products for customers to browse
    '''
    from .models import SurplusDeal
    now = timezone.now()

    products = Product.objects.filter(
        is_active=True,
        availability='available',
    ).annotate(
        is_available_sort=Case(
            When(availability='available', then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    )

    current_month = timezone.now().month

    products = products.annotate(
        is_in_season_annotated=Case(
            When(
                Q(season_start__isnull=True) | Q(season_end__isnull=True),
                then=Value(True)
            ),
            When(
                Q(season_start__lte=current_month) &
                Q(season_end__gte=current_month) &
                Q(season_start__lte=F('season_end')),
                then=Value(True)
            ),
            When(
                Q(season_start__gt=F('season_end')) &
                (Q(season_start__lte=current_month) | Q(season_end__gte=current_month)),
                then=Value(True)
            ),
            default=Value(False),
            output_field=BooleanField()
        )
    ).prefetch_related('surplus_deal')

    # get and apply filters
    organic_filter = request.GET.get('organic') == 'true'
    season_filter = request.GET.get('in_season') == 'true'
    free_from_filter = request.GET.get('free_from') == 'true'
    allergen_filter = request.GET.get('allergen', '')

    if organic_filter:
        products = products.filter(is_organic=True)
    if season_filter:
        products = products.filter(is_in_season_annotated=True)
    if free_from_filter:
        products = products.filter(has_allergens=False)
    if allergen_filter:
        products = products.exclude(allergens__name=allergen_filter)

    search_query = request.GET.get('q', '')
    if search_query:
        # Check if search query contains "organic"
        search_lower = search_query.lower()
        is_organic_search = 'organic' in search_lower

        # Build the base search
        products = products.annotate(
            similarity=TrigramSimilarity('name', search_query)
        )

        # Create filter conditions
        search_filter = Q(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(category__name__icontains=search_query) |
            Q(similarity__gt=0.3)
        )

        products = products.filter(search_filter).order_by('-similarity')

            # TODO:
            ## add producer name when available

    categories = ProductCategory.objects.filter(is_active=True)
    category_value = request.GET.get('category', '').strip()
    selected_category = None
    if category_value:
        if category_value.isdigit():
            selected_category = categories.filter(pk=int(category_value)).first()
        else:
            category_aliases = {'fruit': 'fruits'}
            category_slug = category_aliases.get(category_value.lower(), category_value.lower())
            selected_category = categories.filter(
                Q(slug__iexact=category_slug) | Q(name__iexact=category_slug)
            ).first()

        # Invalid or unavailable category links should render an empty catalogue,
        # never raise "Field 'id' expected a number".
        if selected_category:
            products = products.filter(
                Q(category=selected_category) | Q(category__parent=selected_category)
            )
        else:
            products = products.none()

    # recommend system
    recommended_products = []
    personalized_products = []
    attention_data = {}
    if request.user.is_authenticated:
        try:
            import os
            import requests as _req
            from orders.models import OrderItem

            ml_url = os.environ.get("ML_SERVICE_URL", "http://ml-service:8001")

            order_items = OrderItem.objects.filter(
                producer_order__payment__user_id=request.user.id,
                producer_order__payment__payment_status="paid",
            ).select_related("producer_order__payment").order_by(
                "producer_order__payment__created_at",
                "producer_order__id",
            )
            purchase_history = [
                {
                    "product_id": item.product_id,
                    "timestamp": item.producer_order.payment.created_at.isoformat(),
                }
                for item in order_items
                for _ in range(item.quantity)
            ]

            response = _req.post(
                f"{ml_url}/predict/recommendations/explanation",
                json={"user_id": request.user.id, "purchase_history": purchase_history, "top_k": 6},
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()

            raw_recs = result.get("recommendations", [])
            product_ids = [r["product_id"] for r in raw_recs]
            products_by_id = {
                p.id: p
                for p in Product.objects.filter(id__in=product_ids, availability="available")
            }
            recommended_products = [
                {**r, "product": products_by_id[r["product_id"]], "display_score": r["score"] * 100}
                for r in raw_recs
                if r["product_id"] in products_by_id
            ]

            attention_data = {
                "weights": result.get("attention_weights", []),
                "order_details": result.get("order_details", []),
            }

        except Exception as e:
            print(f"Recommendation error for user {request.user.id}: {e}")
            recommended_products = []
            personalized_products = []

    # products = products.order_by(category_id=category_id)
    # Template will just call product.image_url which checks DB field (demo_image_url).

    # Pagination - 30 products per page
    products = products.order_by('-is_available_sort', 'name') # order by availability (unavailable products show last)

    paginator = Paginator(products, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    product_found = list(products)

    context = {
        'product_found': product_found,
        'products': list(page_obj.object_list),
        'categories': categories,
        'current_categories': str(selected_category.id) if selected_category else category_value,
        'current_category': selected_category.id if selected_category else '',
        'selected_category': selected_category,
        'search_query': search_query,
        'recommended_products': recommended_products,
        'personalized_products': personalized_products,
        'attention_data': attention_data,
        'has_recommendations': bool(recommended_products),
        'has_attention': bool(attention_data),
        'now': now,
        'page_obj': page_obj,
        'allergens': Allergen.objects.all(),
        'active_allergen_filter': allergen_filter,
        'free_from_filter': free_from_filter,
    }
    return render(request, 'products/product_list.html', context)

@login_required
def surplus_analytics(request):
    """TC-019: Producer-facing food waste analytics dashboard."""
    from .models import SurplusDeal
    from mainApp.decorators import producer_required

    if not hasattr(request.user, 'producer_profile'):
        messages.error(request, "Only producers can view surplus analytics.")
        return redirect('mainApp:products:product_list')

    producer = request.user.producer_profile
    deals = SurplusDeal.objects.filter(producer=producer).select_related('product').order_by('-created_at')

    total_deals = deals.count()
    total_units_sold = sum(d.units_sold for d in deals)
    active_deals = deals.filter(is_active=True).count()

    return render(request, 'products/surplus_analytics.html', {
        'deals': deals,
        'total_deals': total_deals,
        'total_units_sold': total_units_sold,
        'active_deals': active_deals,
    })


def surplus_deals(request):
    """TC-019: Customer-facing surplus / last-minute deals listing."""
    from .models import SurplusDeal

    now = timezone.now()
    deals = SurplusDeal.objects.filter(
        is_active=True,
        expires_at__gt=now,
    ).select_related('product__producer', 'product__category').order_by('expires_at')

    return render(request, 'products/surplus_deals.html', {
        'deals': deals,
        'now': now,
    })


def product_detail(request, product_id):
    '''
    Show detailed product
    '''
    from interactions.utils import log_interaction
    from interactions.models import UserInteraction

    product = Product.objects.get(id=product_id)
    log_interaction(request, UserInteraction.PRODUCT_VIEWED, product=product)

    if request.user.is_authenticated:
        user_lat, user_long = request.user.get_default_address_coordinates()
    else:
        user_lat, user_long = BRISTOL_LAT,BRISTOL_LON


    food_miles = product.get_food_miles(user_lat, user_long)

    # TC-020: Recipe suggestions linked to this product
    from producers.models import Recipe
    linked_recipes = Recipe.objects.filter(
        linked_products=product,
        is_published=True,
        moderation_status='approved',
    ).select_related('producer')[:3]

    # TC-019: surplus deal for this product
    active_deal = None
    try:
        deal = product.surplus_deal
        if deal.is_active and deal.expires_at > timezone.now():
            active_deal = deal
    except Exception:
        pass

    # Template will just call product.image_url which checks DB field (demo_image_url).

    context = {
        'product': product,
        'food_miles': food_miles,
        'user_is_authenticated': request.user.is_authenticated,
        'user_has_coordinates': bool(user_lat and user_long),
        'is_deleted': not product.is_active,
        'linked_recipes': linked_recipes,  # TC-020
        'active_deal': active_deal,  # TC-019
    }

    reviews = product.reviews.select_related('customer').all()
    user_has_purchased = False
    user_review = None
    if request.user.is_authenticated:
        from orders.models import OrderItem
        user_has_purchased = OrderItem.objects.filter(
            product=product,
            producer_order__payment__user=request.user,
            producer_order__payment__payment_status='paid',
            producer_order__order_status='delivered',
        ).exists()
        user_review = reviews.filter(customer=request.user).first()

    context.update({
        'reviews': reviews,
        'user_has_purchased': user_has_purchased,
        'user_review': user_review,
    })

    return render(request, 'products/product_detail.html', context)


@login_required
def respond_to_review(request, review_id):
    """TC-024: Allow the product's producer to post a public response to a review."""
    from .models import ProductReview, ProducerReviewResponse
    from mainApp.decorators import producer_required

    review = get_object_or_404(ProductReview, id=review_id)

    if not hasattr(request.user, 'producer_profile'):
        messages.error(request, "Only producers can respond to reviews.")
        return redirect('mainApp:products:product_detail', product_id=review.product_id)

    if review.product.producer != request.user.producer_profile:
        messages.error(request, "You can only respond to reviews of your own products.")
        return redirect('mainApp:products:product_detail', product_id=review.product_id)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            ProducerReviewResponse.objects.update_or_create(
                review=review,
                defaults={'producer': request.user.producer_profile, 'body': body},
            )
            messages.success(request, "Your response has been posted.")
        else:
            messages.error(request, "Response cannot be empty.")

    return redirect('mainApp:products:product_detail', product_id=review.product_id)


@login_required
def submit_review(request, product_id):
    """TC-024: Submit or update a review for a purchased product."""
    product = get_object_or_404(Product, id=product_id)

    from orders.models import OrderItem
    has_purchased = OrderItem.objects.filter(
        product=product,
        producer_order__payment__user=request.user,
        producer_order__payment__payment_status='paid',
        producer_order__order_status='delivered',
    ).exists()

    if not has_purchased:
        messages.error(request, "You can only review products from delivered orders.")
        return redirect('mainApp:products:product_detail', product_id=product_id)

    if request.method == 'POST':
        rating = request.POST.get('rating')
        title = request.POST.get('title', '').strip()
        body = request.POST.get('body', '').strip()

        if not rating or not rating.isdigit() or int(rating) not in range(1, 6):
            messages.error(request, "Please select a rating between 1 and 5.")
            return redirect('mainApp:products:product_detail', product_id=product_id)

        ProductReview.objects.update_or_create(
            product=product,
            customer=request.user,
            defaults={'rating': int(rating), 'title': title, 'body': body},
        )
        messages.success(request, "Your review has been submitted.")

    return redirect('mainApp:products:product_detail', product_id=product_id)


# =============================================================================
# TC-020 — Customer-facing recipe & farm story views
# =============================================================================

def recipe_list(request):
    """List all approved, published recipes."""
    recipes = Recipe.objects.filter(
        is_published=True,
        moderation_status='approved',
    ).select_related('producer').prefetch_related('linked_products', 'seasons')

    search = request.GET.get('q', '')
    if search:
        recipes = recipes.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(ingredients__icontains=search)
        )

    tag = request.GET.get('tag', '')
    if tag:
        recipes = recipes.filter(seasons__slug=tag)

    return render(request, 'products/recipe_list.html', {
        'recipes': recipes,
        'seasons': Season.objects.all().order_by('name'),
        'search': search,
        'active_tag': tag,
    })


def recipe_detail(request, recipe_id):
    """Full recipe detail page."""
    recipe = get_object_or_404(
        Recipe.objects.select_related('producer').prefetch_related('seasons', 'linked_products'),
        id=recipe_id, is_published=True, moderation_status='approved'
    )
    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedRecipe.objects.filter(customer=request.user, recipe=recipe).exists()

    return render(request, 'products/recipe_detail.html', {
        'recipe': recipe,
        'is_saved': is_saved,
    })


@customer_required
def saved_recipes_list(request):
    """List all recipes saved by the logged-in customer."""
    saved = SavedRecipe.objects.filter(
        customer=request.user
    ).select_related('recipe__producer').prefetch_related('recipe__seasons').order_by('-id')
    return render(request, 'products/saved_recipes.html', {'saved': saved})


@customer_required
def toggle_saved_recipe(request, recipe_id):
    """Save or unsave a recipe for the logged-in customer."""
    from producers.models import Recipe, SavedRecipe

    recipe = get_object_or_404(Recipe, id=recipe_id, is_published=True)
    saved, created = SavedRecipe.objects.get_or_create(customer=request.user, recipe=recipe)
    if not created:
        saved.delete()
        messages.success(request, 'Recipe removed from saved.')
    else:
        messages.success(request, 'Recipe saved!')
    return redirect('mainApp:products:recipe_detail', recipe_id=recipe_id)


def producer_stories(request, producer_id):
    """TC-020: Producer profile — farm stories & recipes tab."""
    from mainApp.models import ProducerProfile
    from producers.models import Recipe, FarmStory

    producer = get_object_or_404(ProducerProfile, id=producer_id)
    stories = FarmStory.objects.filter(
        producer=producer, is_published=True, moderation_status='approved'
    ).prefetch_related('images').order_by('-published_at')
    recipes = Recipe.objects.filter(
        producer=producer, is_published=True, moderation_status='approved'
    ).prefetch_related('seasons').order_by('-published_at')

    return render(request, 'products/producer_stories.html', {
        'producer': producer,
        'stories': stories,
        'recipes': recipes,
    })


def all_stories(request):
    """All published farm stories and recipes across every producer."""
    from producers.models import FarmStory, Recipe

    stories = FarmStory.objects.filter(
        is_published=True, moderation_status='approved'
    ).select_related('producer').prefetch_related('images').order_by('-published_at')

    recipes = Recipe.objects.filter(
        is_published=True, moderation_status='approved'
    ).select_related('producer').prefetch_related('seasons').order_by('-published_at')

    return render(request, 'products/all_stories.html', {
        'stories': stories,
        'recipes': recipes,
    })
