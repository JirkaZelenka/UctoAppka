from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0006_remove_category_description_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvestmentObservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('observed_value', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Pozorovaná hodnota')),
                ('observation_date', models.DateField(verbose_name='Datum pozorované hodnoty')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('investment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='observations', to='expenses.investment', verbose_name='Investiční skupina')),
            ],
            options={
                'verbose_name': 'Pozorování investice',
                'verbose_name_plural': 'Pozorování investic',
                'ordering': ['-observation_date', '-created_at'],
            },
        ),
    ]
