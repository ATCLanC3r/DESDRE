from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainApp', '0019_merge_migrations'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(blank=True, max_length=255)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, protocol='both', unpack_ipv4=True)),
                ('success', models.BooleanField(default=False)),
                ('attempted_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-attempted_at'],
            },
        ),
        migrations.AddIndex(
            model_name='loginattempt',
            index=models.Index(fields=['ip_address', 'attempted_at'], name='mainapp_log_ip_addr_idx'),
        ),
    ]
