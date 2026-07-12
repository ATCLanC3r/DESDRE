def notification_count(request):
    count = 0
    if request.user.is_authenticated:
        try:
            count = request.user.notifications.filter(is_read=False).count()
        except Exception:
            count = 0
    return {"notification_count": count}
