from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsProducerOwnerOrReadOnly(BasePermission):
    """Allow public reads and restrict product changes to the owning producer."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "producer"
            and hasattr(request.user, "producer_profile")
        )

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return bool(obj.producer and obj.producer.user_id == request.user.id)

