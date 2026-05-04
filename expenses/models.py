from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class CategoryType(models.TextChoices):
    INCOME = 'INCOME', 'Příjem'
    EXPENSE = 'EXPENSE', 'Výdaj'


class Category(models.Model):
    """Kategorie výdajů"""
    type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        default=CategoryType.EXPENSE,
        verbose_name="Typ",
    )
    name = models.CharField(max_length=100, verbose_name="Název kategorie")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorie"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Subcategory(models.Model):
    """Subkategorie výdajů"""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories', verbose_name="Kategorie")
    name = models.CharField(max_length=100, verbose_name="Název subkategorie")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Subkategorie"
        verbose_name_plural = "Subkategorie"
        ordering = ['category', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"],
                name="unique_subcategory_name_per_category",
            ),
        ]
    
    def __str__(self):
        return f"{self.category.name} - {self.name}"


class TransactionType(models.TextChoices):
    """Typ transakce"""
    INCOME = 'INCOME', 'Příjem'
    EXPENSE = 'EXPENSE', 'Výdaj'
    INVESTMENT = 'INVESTMENT', 'Investice (přesun)'


class PaymentFor(models.TextChoices):
    """Za koho je placeno"""
    SELF = 'SELF', 'Za sebe'
    PARTNER = 'PARTNER', 'Za partnera'
    SHARED = 'SHARED', 'Společný účet'


class Transaction(models.Model):
    """Transakce - příjem, výdaj nebo investice"""
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Částka")
    description = models.CharField(max_length=200, verbose_name="Popis")
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.EXPENSE,
        verbose_name="Typ"
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Kategorie")
    subcategory = models.ForeignKey(Subcategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Subkategorie")
    
    # Pro výdaje - na kolik měsíců (pro předplatná)
    is_recurring = models.BooleanField(default=False, verbose_name="Opakující se")
    months_duration = models.IntegerField(default=0, verbose_name="Na kolik měsíců (0 = jednorázové)")
    
    # Datumy
    date = models.DateField(default=timezone.now, verbose_name="Datum")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Datum a čas zapsání")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Datum a čas editace")
    
    # Kdo a za koho
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='transactions_created', verbose_name="Kdo zapsal")
    payment_for = models.CharField(
        max_length=20,
        choices=PaymentFor.choices,
        default=PaymentFor.SELF,
        verbose_name="Za koho placeno"
    )
    
    # Další
    note = models.TextField(blank=True, verbose_name="Poznámka")
    approved = models.BooleanField(default=False, verbose_name="Schváleno")
    is_imported = models.BooleanField(default=False, verbose_name="Importováno")
    is_deleted = models.BooleanField(default=False, verbose_name="Smazáno")
    
    # Pro investice - link na investiční skupinu
    investment = models.ForeignKey('Investment', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name="Investiční skupina")
    institution = models.ForeignKey(
        'Institution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        verbose_name="Instituce",
    )
    
    class Meta:
        verbose_name = "Transakce"
        verbose_name_plural = "Transakce"
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} Kč - {self.description}"


class RecurringPayment(models.Model):
    """Trvalé platby - předplatná, nájem, atd. (orientační plán, nezávislý na transakcích)."""
    name = models.CharField(max_length=200, verbose_name="Název")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Částka")
    frequency_months = models.IntegerField(default=1, verbose_name="Frekvence (měsíce)")
    start_date = models.DateField(verbose_name="Počáteční datum platby")
    active = models.BooleanField(default=True, verbose_name="Aktivní")
    permanent = models.BooleanField(
        default=False,
        verbose_name="Trvalé",
        help_text="Dlouhodobá závazná platba, obtížně zrušitelná",
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_payments",
        verbose_name="Vlastník",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Trvalá platba"
        verbose_name_plural = "Trvalé platby"
        ordering = ['start_date', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.amount} Kč / {self.frequency_months} měs."


class RecurringPaymentPaidDate(models.Model):
    """Označení, že konkrétní naplánovaný termín trvalé platby byl uhrazen (orientační)."""
    recurring_payment = models.ForeignKey(
        RecurringPayment,
        on_delete=models.CASCADE,
        related_name='paid_dates',
        verbose_name="Trvalá platba",
    )
    due_date = models.DateField(verbose_name="Datum splátky")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Uhrazený termín trvalé platby"
        verbose_name_plural = "Uhrazené termíny trvalých plateb"
        constraints = [
            models.UniqueConstraint(
                fields=['recurring_payment', 'due_date'],
                name='uniq_recurring_payment_due_date',
            ),
        ]
    
    def __str__(self):
        return f"{self.recurring_payment_id} @ {self.due_date}"


class Institution(models.Model):
    """Banka, pojišťovna, poskytovatel služeb apod."""
    name = models.CharField(max_length=200, verbose_name="Jméno")
    service_description = models.TextField(blank=True, verbose_name="Popis služby")
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='institutions',
        verbose_name="Vlastník",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena")
    frequency = models.CharField(max_length=200, blank=True, verbose_name="Frekvence")
    start_date = models.DateField(null=True, blank=True, verbose_name="Start")
    end_date = models.DateField(null=True, blank=True, verbose_name="Konec")
    contact = models.TextField(blank=True, verbose_name="Kontakt")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Instituce"
        verbose_name_plural = "Instituce"
        ordering = ['name', 'id']

    def __str__(self):
        return self.name


class Investment(models.Model):
    """Investiční skupina/typ - pouze název skupiny, transakce se přidávají na stránce transakcí"""
    name = models.CharField(max_length=200, verbose_name="Název investiční skupiny")
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='investments',
        verbose_name="Vlastník",
    )
    observed_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Pozorovaná hodnota")
    observed_value_date = models.DateField(null=True, blank=True, verbose_name="Datum pozorované hodnoty")
    note = models.TextField(blank=True, verbose_name="Poznámka")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Investiční skupina"
        verbose_name_plural = "Investiční skupiny"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    @property
    def invested_amount(self):
        """Součet všech transakcí spojených s touto investicí"""
        from django.db.models import Sum
        total = self.transactions.filter(transaction_type=TransactionType.INVESTMENT).aggregate(
            total=Sum('amount')
        )['total']
        return total or Decimal('0')

    @property
    def latest_observation(self):
        """Nejnovější pozorování podle data a času vytvoření."""
        return self.observations.order_by('-observation_date', '-created_at').first()
    
    @property
    def profit_loss(self):
        """Zisk/ztráta"""
        latest = self.latest_observation
        value = latest.observed_value if latest else self.observed_value
        if value:
            return value - self.invested_amount
        return None
    
    @property
    def profit_loss_percent(self):
        """Zisk/ztráta v procentech"""
        invested = self.invested_amount
        latest = self.latest_observation
        value = latest.observed_value if latest else self.observed_value
        if value and invested:
            return ((value - invested) / invested) * 100
        return None


class InvestmentObservation(models.Model):
    """Historie pozorovaných hodnot investiční skupiny."""
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='observations',
        verbose_name="Investiční skupina",
    )
    observed_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Pozorovaná hodnota")
    observation_date = models.DateField(verbose_name="Datum pozorované hodnoty")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pozorování investice"
        verbose_name_plural = "Pozorování investic"
        ordering = ['-observation_date', '-created_at']

    def __str__(self):
        return f"{self.investment.name} - {self.observed_value} Kč ({self.observation_date})"


class BudgetLimit(models.Model):
    """Limity a varování pro kategorie"""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budget_limits', verbose_name="Kategorie")
    monthly_limit = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Měsíční limit")
    warning_threshold = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Varování při překročení")
    active = models.BooleanField(default=True, verbose_name="Aktivní")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Budget limit"
        verbose_name_plural = "Budget limity"
    
    def __str__(self):
        return f"{self.category.name} - limit {self.monthly_limit} Kč"

