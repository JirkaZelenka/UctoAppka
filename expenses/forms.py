from django import forms
from django.utils import timezone
from datetime import date
from .models import (
    Transaction, Category, Subcategory, Investment, InvestmentObservation,
    RecurringPayment, TransactionType, PaymentFor
)


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            'amount', 'description', 'transaction_type', 'category', 'subcategory',
            'months_duration', 'date', 'payment_for', 'note', 'is_recurring', 'approved', 'investment'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control amount-input',
                'step': '1', 
                'min': '1',
                'pattern': '[0-9]*',
                'inputmode': 'numeric'
            }),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'subcategory': forms.Select(attrs={'class': 'form-control'}),
            'months_duration': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '12'}),
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'payment_for': forms.Select(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'investment': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'amount': 'Částka (Kč)',
            'description': 'Popis',
            'transaction_type': 'Typ',
            'category': 'Kategorie',
            'subcategory': 'Subkategorie',
            'months_duration': 'Na kolik měsíců (0 = jednorázové)',
            'date': 'Datum',
            'payment_for': 'Za koho placeno',
            'note': 'Poznámka',
            'is_recurring': 'Trvalá platba',
            'approved': 'Schváleno',
            'investment': 'Investiční skupina (pouze pro typ Investice)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial_date = self.initial.get('date') or self.instance.date or timezone.now().date()
        if isinstance(initial_date, date):
            initial_date = initial_date.strftime('%Y-%m-%d')
        self.fields['date'].input_formats = ['%Y-%m-%d']
        self.fields['date'].initial = initial_date
        self.fields['approved'].disabled = not (self.instance and self.instance.pk)
        self.fields['approved'].required = False
        self.fields['amount'].required = True
        self.fields['description'].required = True
        self.fields['transaction_type'].required = True
        self.fields['category'].required = True
        self.fields['subcategory'].required = True
        self.fields['date'].required = True
        self.fields['payment_for'].required = True
        self.fields['months_duration'].required = True
        self.fields['payment_for'].choices = [
            (PaymentFor.SELF, 'Sám'),
            (PaymentFor.SHARED, 'Společný'),
        ]

        selected_type = (
            self.data.get('transaction_type')
            if self.data
            else self.initial.get('transaction_type') or self.instance.transaction_type or TransactionType.EXPENSE
        )
        self.fields['category'].queryset = Category.objects.filter(type=selected_type).order_by('name')

        selected_category = self.data.get('category') if self.data else self.initial.get('category') or getattr(self.instance, 'category_id', None)
        if selected_category:
            self.fields['subcategory'].queryset = Subcategory.objects.filter(category_id=selected_category).order_by('name')
        else:
            self.fields['subcategory'].queryset = Subcategory.objects.none()

        # Format amount as integer when displaying
        if self.instance and self.instance.pk and self.instance.amount:
            self.initial['amount'] = int(round(float(self.instance.amount)))
    
    def clean_amount(self):
        """Convert amount to integer (round to nearest)"""
        amount = self.cleaned_data.get('amount')
        if amount is not None:
            from decimal import Decimal
            # Round to nearest integer
            if amount <= 0:
                raise forms.ValidationError("Částka musí být větší než 0.")
            return Decimal(int(round(float(amount))))
        return amount

    def clean_months_duration(self):
        months = self.cleaned_data.get('months_duration')
        if months is None:
            return 0
        if months < 0 or months > 12:
            raise forms.ValidationError("Počet měsíců musí být mezi 0 a 12.")
        return months

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        subcategory = cleaned_data.get('subcategory')
        transaction_type = cleaned_data.get('transaction_type')

        if category and transaction_type and category.type != transaction_type:
            self.add_error('category', 'Kategorie neodpovídá zvolenému typu transakce.')

        if category and subcategory and subcategory.category_id != category.id:
            self.add_error('subcategory', 'Subkategorie nepatří do vybrané kategorie.')

        # New transactions always start as unapproved.
        if not self.instance.pk:
            cleaned_data['approved'] = False

        return cleaned_data


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['type', 'name']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'type': 'Typ',
            'name': 'Název kategorie',
        }


class SubcategoryForm(forms.ModelForm):
    class Meta:
        model = Subcategory
        fields = ['category', 'name']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'category': 'Kategorie',
            'name': 'Název subkategorie',
        }

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError("Název subkategorie je povinný.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        name = cleaned_data.get('name')
        if category and name:
            exists = Subcategory.objects.filter(category=category, name__iexact=name)
            if self.instance.pk:
                exists = exists.exclude(pk=self.instance.pk)
            if exists.exists():
                self.add_error('name', 'Subkategorie s tímto názvem už v této kategorii existuje.')
        return cleaned_data


class InvestmentForm(forms.ModelForm):
    class Meta:
        model = Investment
        fields = ['name', 'owner', 'note']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'owner': forms.Select(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'name': 'Název investiční skupiny',
            'owner': 'Vlastník',
            'note': 'Poznámka',
        }


class InvestmentValueForm(forms.ModelForm):
    """Formulář pro aktualizaci pozorované hodnoty investice"""
    class Meta:
        model = InvestmentObservation
        fields = ['observed_value', 'observation_date']
        widgets = {
            'observed_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'observation_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
        }
        labels = {
            'observed_value': 'Pozorovaná hodnota (Kč)',
            'observation_date': 'Datum pozorované hodnoty',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['observation_date'].input_formats = ['%Y-%m-%d']


class RecurringPaymentForm(forms.ModelForm):
    class Meta:
        model = RecurringPayment
        fields = [
            'name', 'amount', 'transaction_type', 'category', 'subcategory', 'frequency_months',
            'next_payment_date', 'payment_for', 'active', 'note'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'subcategory': forms.Select(attrs={'class': 'form-control'}),
            'frequency_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'next_payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_for': forms.Select(attrs={'class': 'form-control'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'name': 'Název',
            'amount': 'Částka (Kč)',
            'transaction_type': 'Typ',
            'category': 'Kategorie',
            'subcategory': 'Subkategorie',
            'frequency_months': 'Frekvence (měsíce)',
            'next_payment_date': 'Datum další platby',
            'payment_for': 'Za koho placeno',
            'active': 'Aktivní',
            'note': 'Poznámka',
        }

