# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0004_recurringpayment_transaction_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='is_imported',
            field=models.BooleanField(default=False, verbose_name='Importováno'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='is_deleted',
            field=models.BooleanField(default=False, verbose_name='Smazáno'),
        ),
    ]

