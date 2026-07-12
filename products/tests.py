from django.test import TestCase
from django.urls import reverse

from products.models import ProductCategory


class HomepageCategoryLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, slug in (
            ('Vegetables', 'vegetables'),
            ('Fruits', 'fruits'),
            ('Dairy', 'dairy'),
        ):
            ProductCategory.objects.create(name=name, slug=slug, is_active=True)

    def test_homepage_category_slugs_render_without_error(self):
        url = reverse('mainApp:products:product_list')
        for slug in ('vegetables', 'fruits', 'dairy', 'bakery'):
            with self.subTest(slug=slug):
                response = self.client.get(url, {'category': slug})
                self.assertEqual(response.status_code, 200)

    def test_singular_fruit_alias_is_supported(self):
        response = self.client.get(
            reverse('mainApp:products:product_list'), {'category': 'fruit'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_category'].slug, 'fruits')

    def test_numeric_sidebar_category_filter_still_works(self):
        category = ProductCategory.objects.get(slug='vegetables')
        response = self.client.get(
            reverse('mainApp:products:product_list'), {'category': category.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_category'], category)

    def test_modern_story_landing_page_renders(self):
        response = self.client.get(reverse('mainApp:products:all_stories'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Field notes &amp; good food.')
        self.assertTemplateUsed(response, 'products/all_stories.html')

    def test_modern_recipe_landing_page_renders(self):
        response = self.client.get(reverse('mainApp:products:recipe_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recipes for the season.')
        self.assertTemplateUsed(response, 'products/recipe_list.html')

# Create your tests here.
