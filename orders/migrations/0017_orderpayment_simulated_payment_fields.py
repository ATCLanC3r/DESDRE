from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0016_merge_0014_add_bulk_and_recurring_orders_0015_orderproducer_settled_at")]

    operations = [
        migrations.AddField(
            model_name="orderpayment",
            name="payment_reference",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="orderpayment",
            name="payment_method",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="orderpayment",
            name="masked_payment_details",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
