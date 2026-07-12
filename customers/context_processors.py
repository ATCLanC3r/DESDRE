from django.db.models import Sum

def cart_count(request):
    count = 0
    if request.user.is_authenticated:
        try:
            cart = getattr(request.user, "cart", None)
            if cart:
                # count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0
                count = cart.items.count()
        except Exception:
            count = 0
    return {"cart_count": count}