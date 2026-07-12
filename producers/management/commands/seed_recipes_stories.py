from django.core.management.base import BaseCommand
from producers.models import Recipe, FarmStory, Season
from mainApp.models import ProducerProfile
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed recipes and farm stories with sample data'

    def handle(self, *args, **options):
        # Get existing producers
        producers = list(ProducerProfile.objects.all())
        if not producers:
            self.stdout.write(self.style.ERROR('No producers found. Please run seed_producers first.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Found {len(producers)} producers'))

        # Get seasons
        seasons = {s.slug: s for s in Season.objects.all()}
        if not seasons:
            self.stdout.write(self.style.ERROR('No seasons found. Please run seed_seasons first.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Found {len(seasons)} seasons: {list(seasons.keys())}'))

        # Sample recipes data
        recipes_data = [
            {
                'title': 'Summer Berry Tart',
                'description': 'A delicious fresh berry tart perfect for summer gatherings',
                'ingredients': '2 cups fresh strawberries\n1 cup blueberries\n1 cup raspberries\n1 cup flour\n1/2 cup butter\n1/4 cup sugar\n1 tsp vanilla',
                'instructions': '1. Make the tart crust by mixing flour, butter, and sugar.\n2. Roll out the dough and place in tart pan.\n3. Bake for 15 minutes at 180C.\n4. Let cool, then arrange fresh berries on top.\n5. Brush with warmed jam for shine.',
                'seasons': ['summer'],
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Autumn Squash Soup',
                'description': 'Hearty butternut squash soup perfect for chilly autumn evenings',
                'ingredients': '1 large butternut squash\n1 onion\n2 cloves garlic\n4 cups vegetable stock\n1/2 cup cream\nSalt and pepper to taste',
                'instructions': '1. Peel and cube the squash.\n2. Saute onion and garlic until soft.\n3. Add squash and stock, simmer 20 minutes.\n4. Blend until smooth.\n5. Stir in cream and season to taste.',
                'seasons': ['autumn'],
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Winter Root Vegetable Roast',
                'description': 'A warming mix of roasted root vegetables for winter tables',
                'ingredients': '2 carrots\n2 parsnips\n1 swede\n2 potatoes\n3 tbsp olive oil\nFresh rosemary\nSalt and pepper',
                'instructions': '1. Preheat oven to 200C.\n2. Peel and cut all vegetables into chunks.\n3. Toss with olive oil, rosemary, salt, and pepper.\n4. Spread on baking tray.\n5. Roast for 45 minutes until golden.',
                'seasons': ['winter'],
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Spring Asparagus Risotto',
                'description': 'Creamy risotto featuring fresh spring asparagus',
                'ingredients': '1 bunch fresh asparagus\n300g arborio rice\n1 litre vegetable stock\n1 onion\n1/2 cup parmesan\nWhite wine',
                'instructions': '1. Trim asparagus and cut into pieces.\n2. Saute onion, add rice and toast briefly.\n3. Add wine and let absorb.\n4. Gradually add stock, stirring.\n5. Add asparagus in last 5 minutes.\n6. Finish with parmesan.',
                'seasons': ['spring'],
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Summer Tomato Basil Salad',
                'description': 'Simple and refreshing salad showcasing summer tomatoes',
                'ingredients': '4 large tomatoes\n1 bunch fresh basil\n2 tbsp olive oil\n1 tbsp balsamic vinegar\nSalt and pepper\nMozzarella balls',
                'instructions': '1. Slice tomatoes into rounds.\n2. Arrange on plate with basil leaves.\n3. Add mozzarella balls.\n4. Drizzle with olive oil and balsamic.\n5. Season with salt and pepper.',
                'seasons': ['summer', 'spring'],
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Classic Apple Pie',
                'description': 'Traditional apple pie with seasonal apples',
                'ingredients': '6 medium apples\n1 cup sugar\n1 tsp cinnamon\n2 pie crusts\n2 tbsp butter\n1 tbsp flour',
                'instructions': '1. Peel and slice apples.\n2. Mix with sugar, cinnamon, and flour.\n3. Place one crust in pie dish.\n4. Add apple filling, dot with butter.\n5. Cover with second crust and seal.\n6. Bake at 190C for 45 minutes.',
                'seasons': ['autumn', 'winter'],
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Fresh Farm Eggs Breakfast',
                'description': 'A simple breakfast recipe using fresh farm eggs',
                'ingredients': '4 fresh eggs\nButter\nSalt and pepper\nFresh herbs\nToast',
                'instructions': '1. Heat butter in pan over medium heat.\n2. Crack eggs into pan.\n3. Cook to desired doneness.\n4. Season with salt, pepper, fresh herbs.\n5. Serve with toast.',
                'seasons': ['spring', 'summer', 'autumn', 'winter'],
                'status': 'pending',
                'published': False,
            },
            {
                'title': 'Seasonal Vegetable Stir Fry',
                'description': 'Quick and healthy stir fry with seasonal vegetables',
                'ingredients': '2 cups mixed seasonal vegetables\n2 tbsp soy sauce\n1 tbsp sesame oil\nGinger and garlic\nRice',
                'instructions': '1. Wash and cut vegetables into bite-sized pieces.\n2. Heat sesame oil in wok.\n3. Add ginger and garlic, stir 30 seconds.\n4. Add vegetables and stir fry 5 minutes.\n5. Add soy sauce, toss, serve over rice.',
                'seasons': ['spring', 'summer'],
                'status': 'rejected',
                'published': False,
            },
        ]

        # Sample farm stories data
        stories_data = [
            {
                'title': 'Our Harvest Festival',
                'body': 'Every autumn, our farm hosts a wonderful harvest festival where neighbors and friends come together to celebrate the season\'s bounty. We display our finest produce, share recipes, and enjoy live music. It\'s a time when the community truly comes alive. This year was especially special as we introduced our new pumpkin patch to the delight of families with children.',
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'A Day on the Farm',
                'body': 'Welcome to a typical day at our farm! We start at dawn, checking on all our animals and surveying the crops. Our day involves feeding the chickens, milking the cows, and tending to the vegetable gardens. We take pride in sustainable practices and animal welfare. Every season brings its own rhythm and rewards.',
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Growing Organic Produce',
                'body': 'Our journey to fully organic farming began five years ago. We made the decision to transition after learning more about the impact of conventional farming on soil health and biodiversity. Today, our farm is certified organic, and we\'re proud to offer produce that\'s grown without synthetic pesticides or fertilizers. The quality speaks for itself!',
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'Welcome to Our Family Farm',
                'body': 'Our family has been farming this land for three generations. What started as a smallholding has grown into a thriving organic farm that supplies our local community. We believe in traditional farming methods combined with modern sustainable practices. Our mission is to provide the freshest, most nutritious produce while caring for the land.',
                'status': 'pending',
                'published': False,
            },
            {
                'title': 'Sustainable Farming Practices',
                'body': 'Sustainability is at the heart of everything we do. We practice crop rotation to maintain soil fertility, use rainwater harvesting systems, and maintain wildflower margins to support pollinators. Our composting system turns waste into valuable fertilizer. We\'re constantly learning and improving our practices to minimize our environmental footprint.',
                'status': 'approved',
                'published': True,
            },
            {
                'title': 'From Field to Table',
                'body': 'We believe that knowing where your food comes from makes it taste better. That\'s why we\'re passionate about connecting our customers directly to the source. When you buy from our farm, you\'re not just getting vegetables - you\'re getting a connection to the land, the seasons, and the hard work that brings food to your table.',
                'status': 'rejected',
                'published': False,
            },
        ]

        # Create recipes
        self.stdout.write(self.style.SUCCESS('\nCreating recipes...'))
        recipes_created = 0
        for data in recipes_data:
            producer = data.get('producer', producers[recipes_created % len(producers)])
            recipe, created = Recipe.objects.get_or_create(
                title=data['title'],
                producer=producer,
                defaults={
                    'description': data['description'],
                    'ingredients': data['ingredients'],
                    'instructions': data['instructions'],
                    'moderation_status': data['status'],
                    'is_published': data['published'],
                }
            )
            if created:
                # Set seasons
                recipe.seasons.set([seasons[slug] for slug in data['seasons'] if slug in seasons])
                recipe.full_clean()
                recipe.save()
                recipes_created += 1
                status_str = f"{data['status']}" + (", published" if data['published'] else "")
                self.stdout.write(f"  Created recipe: {recipe.title} ({status_str})")
            else:
                self.stdout.write(f"  Skipped: {data['title']} (already exists)")

        # Create farm stories
        self.stdout.write(self.style.SUCCESS('\nCreating farm stories...'))
        stories_created = 0
        for i, data in enumerate(stories_data):
            producer = producers[i % len(producers)]
            story, created = FarmStory.objects.get_or_create(
                title=data['title'],
                producer=producer,
                defaults={
                    'body': data['body'],
                    'moderation_status': data['status'],
                    'is_published': data['published'],
                }
            )
            if created:
                story.full_clean()
                story.save()
                stories_created += 1
                status_str = f"{data['status']}" + (", published" if data['published'] else "")
                self.stdout.write(f"  Created story: {story.title} ({status_str})")
            else:
                self.stdout.write(f"  Skipped: {data['title']} (already exists)")

        self.stdout.write(self.style.SUCCESS(f'\nSeeding complete!'))
        self.stdout.write(f'  Recipes: {recipes_created} created')
        self.stdout.write(f'  Farm Stories: {stories_created} created')