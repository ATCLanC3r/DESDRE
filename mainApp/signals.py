# mainApp/signals.py
from django.core.signals import request_finished
from django.dispatch import receiver
from mainApp.models import (
    RegularUser, ProducerProfile, CustomerProfile,
    CommunityMemberProfile, RestaurantProfile,
)
from django.db.models.signals import post_save, pre_delete, post_delete
from customers.models import Cart

'''
Design issue:
-   Customer model is attached to the customer profile which means that all the other customer profile
    need the base customer profile aswell.

Unless refractoring the cart model to attach to the base User class, we'll have to do the above.
'''
@receiver(post_save, sender=RegularUser)
def create_profiles(sender, instance, created, **kwargs):

    if created:
        if instance.role == RegularUser.Role.PRODUCER:
            ProducerProfile.objects.get_or_create(user=instance)
        elif instance.role == RegularUser.Role.CUSTOMER:
            CustomerProfile.objects.get_or_create(user=instance)
        elif instance.role == RegularUser.Role.COMMUNITY_MEMBER:
            CommunityMemberProfile.objects.get_or_create(user=instance)
        elif instance.role == RegularUser.Role.RESTAURANT:
            RestaurantProfile.objects.get_or_create(
                user=instance,
                defaults={'business_name': instance.get_full_name() or instance.username}
            )

        print("mainApp__create_profiles: Signal ran!")
    
#
# cart signal
#
@receiver(post_save, sender=RegularUser)
def create_cart_for_all_users(sender, instance, created, **kwargs):
    """
    Automatically create a Cart for all users.
    All roles (customer, producer, restaurant, community_member) can shop.
    """
    if not created:
        return
    # Create cart for all users
    Cart.objects.get_or_create(user=instance)
    print(f"mainApp__create_cart: Cart created for {instance.username} ({instance.role})")


@receiver(pre_delete, sender=RegularUser)
def delete_cart_on_user_delete(sender, instance, **kwargs):
    """
    Delete Cart when RegularUser is deleted.
    This handles hard deletes. For soft deletes, call cart deletion in soft_delete() method.
    """
    if hasattr(instance, 'cart'):
        try:
            instance.cart.delete()
            print(f"mainApp__delete_cart: Cart deleted for {instance.username}")
        except Exception as e:
            print(f"mainApp__delete_cart: Failed to delete cart for {instance.username}: {e}")
