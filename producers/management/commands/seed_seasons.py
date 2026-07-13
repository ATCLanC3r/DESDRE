from django.core.management.base import BaseCommand
from producers.models import Season


class Command(BaseCommand):
    help = 'Seed default seasons for recipe categorization'

    def handle(self, *args, **options):
        seasons = [
                ('spring', 'Spring', 1),
                ('summer', 'Summer', 2),
                ('autumn', 'Autumn', 3),
                ('winter', 'Winter', 4),
            ]

        for slug, name, order in seasons:
            season, created = Season.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'display_order': order}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created season: {name}'))
            else:
                self.stdout.write(f'Already exists: {name}')

        self.stdout.write(self.style.SUCCESS('Seeding complete!'))