# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0008_investment_owner'),
    ]

    operations = [
        migrations.RenameField(
            model_name='recurringpayment',
            old_name='next_payment_date',
            new_name='start_date',
        ),
        migrations.AlterField(
            model_name='recurringpayment',
            name='start_date',
            field=models.DateField(verbose_name='Počáteční datum platby'),
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='recurring_payment',
        ),
        migrations.CreateModel(
            name='RecurringPaymentPaidDate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('due_date', models.DateField(verbose_name='Datum splátky')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'recurring_payment',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='paid_dates',
                        to='expenses.recurringpayment',
                        verbose_name='Trvalá platba',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Uhrazený termín trvalé platby',
                'verbose_name_plural': 'Uhrazené termíny trvalých plateb',
            },
        ),
        migrations.AddConstraint(
            model_name='recurringpaymentpaiddate',
            constraint=models.UniqueConstraint(fields=('recurring_payment', 'due_date'), name='uniq_recurring_payment_due_date'),
        ),
    ]
