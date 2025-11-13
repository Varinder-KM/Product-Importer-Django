from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX IF NOT EXISTS product_lower_sku_unique "
                "ON products_product (LOWER(sku));"
            ),
            reverse_sql="DROP INDEX IF EXISTS product_lower_sku_unique;",
        ),
    ]

