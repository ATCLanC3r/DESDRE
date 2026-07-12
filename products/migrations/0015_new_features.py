import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainApp', '0019_merge_migrations'),
        ('products', '0014_merge_migrations'),
    ]

    operations = [
        # TC-019: units_sold tracking on SurplusDeal
        migrations.AddField(
            model_name='surplusdeal',
            name='units_sold',
            field=models.PositiveIntegerField(default=0, help_text='Units sold at the discounted price'),
        ),
        # TC-024: producer responses to reviews
        migrations.CreateModel(
            name='ProducerReviewResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('producer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='review_responses',
                    to='mainApp.producerprofile',
                )),
                ('review', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='producer_response',
                    to='products.productreview',
                )),
            ],
        ),
    ]
