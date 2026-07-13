from django.core.management.base import BaseCommand
from django.db import transaction

from mainApp.models import ProducerProfile


class Command(BaseCommand):
    help = "Merge producer profiles with duplicate business names into the oldest profile."

    @transaction.atomic
    def handle(self, *args, **options):
        duplicate_names = (
            ProducerProfile.objects.exclude(business_name="")
            .values_list("business_name", flat=True)
            .order_by("business_name")
        )
        names = sorted({name for name in duplicate_names if duplicate_names.filter(business_name=name).count() > 1})

        if not names:
            self.stdout.write(self.style.SUCCESS("No duplicate producer stores found."))
            return

        relations = ProducerProfile._meta.related_objects
        for name in names:
            profiles = list(
                ProducerProfile.objects.select_for_update()
                .filter(business_name=name)
                .order_by("id")
            )
            keeper = profiles[0]
            for duplicate in profiles[1:]:
                moved = 0
                for relation in relations:
                    field_name = relation.field.name
                    queryset = relation.related_model.objects.filter(**{field_name: duplicate})
                    count = queryset.count()
                    if count:
                        queryset.update(**{field_name: keeper})
                        moved += count

                username = duplicate.user.username
                duplicate.user.delete()
                duplicate.delete()
                self.stdout.write(
                    f'Merged producer #{duplicate.id} ({username}) into '
                    f'#{keeper.id} ({keeper.user.username}); transferred {moved} linked records.'
                )

        self.stdout.write(self.style.SUCCESS("Duplicate producer accounts merged successfully."))
