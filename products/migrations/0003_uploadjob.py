from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_lower_sku_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="UploadJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task_id", models.CharField(max_length=64, unique=True)),
                ("filename", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("total_rows", models.IntegerField(blank=True, null=True)),
                ("processed_rows", models.IntegerField(default=0)),
                ("errors_json", models.JSONField(blank=True, default=list)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]

