# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0003_transaction_recurring_payment'),
    ]

    operations = [
        migrations.AddField(
            model_name='recurringpayment',
            name='transaction_type',
            field=models.CharField(
                choices=[('INCOME', 'Příjem'), ('EXPENSE', 'Výdaj'), ('INVESTMENT', 'Investice (přesun)')],
                default='EXPENSE',
                max_length=20,
                verbose_name='Typ'
            ),
        ),
    ]

