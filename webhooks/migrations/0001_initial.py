from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Webhook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('url', models.URLField()),
                ('event_type', models.CharField(choices=[('product.created', 'Product Created'), ('product.updated', 'Product Updated'), ('product.deleted', 'Product Deleted'), ('product.import_progress', 'Product Import Progress'), ('product.import_completed', 'Product Import Completed'), ('webhook.test', 'Webhook Test')], max_length=64)),
                ('enabled', models.BooleanField(default=True)),
                ('last_status_code', models.IntegerField(blank=True, null=True)),
                ('last_response_time_ms', models.IntegerField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WebhookDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(max_length=64)),
                ('payload', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('in_progress', 'In Progress'), ('success', 'Success'), ('retry', 'Retrying'), ('failed', 'Failed')], default='pending', max_length=32)),
                ('attempt', models.PositiveIntegerField(default=0)),
                ('max_attempts', models.PositiveIntegerField(default=5)),
                ('response_code', models.IntegerField(blank=True, null=True)),
                ('response_time_ms', models.IntegerField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('next_retry_at', models.DateTimeField(blank=True, null=True)),
                ('is_test', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('webhook', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='deliveries', to='webhooks.webhook')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]

