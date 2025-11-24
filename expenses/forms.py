from django import forms
from .models import (
    Transaction, Category, Subcategory, Investment, 
    RecurringPayment, TransactionType, PaymentFor
)


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            'amount', 'description', 'transaction_type', 'category', 'subcategory',
            'months_duration', 'date', 'payment_for', 'note', 'approved', 'investment'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '1', 
                'min': '0',
                'pattern': '[0-9]*',
                'inputmode': 'numeric'
            }),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'subcategory': forms.Select(attrs={'class': 'form-control'}),
            'months_duration': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_for': forms.Select(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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
            'approved': 'Schváleno',
            'investment': 'Investiční skupina (pouze pro typ Investice)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Format amount as integer when displaying
        if self.instance and self.instance.pk and self.instance.amount:
            self.initial['amount'] = int(round(float(self.instance.amount)))
    
    def clean_amount(self):
        """Convert amount to integer (round to nearest)"""
        amount = self.cleaned_data.get('amount')
        if amount is not None:
            from decimal import Decimal
            # Round to nearest integer
            return Decimal(int(round(float(amount))))
        return amount


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'name': 'Název kategorie',
            'description': 'Popis',
        }


class SubcategoryForm(forms.ModelForm):
    class Meta:
        model = Subcategory
        fields = ['category', 'name', 'description']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'category': 'Kategorie',
            'name': 'Název subkategorie',
            'description': 'Popis',
        }


class InvestmentForm(forms.ModelForm):
    class Meta:
        model = Investment
        fields = ['name', 'note']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'name': 'Název investiční skupiny',
            'note': 'Poznámka',
        }


class InvestmentValueForm(forms.ModelForm):
    """Formulář pro aktualizaci pozorované hodnoty investice"""
    class Meta:
        model = Investment
        fields = ['observed_value', 'observed_value_date']
        widgets = {
            'observed_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'observed_value_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
        labels = {
            'observed_value': 'Pozorovaná hodnota (Kč)',
            'observed_value_date': 'Datum pozorované hodnoty',
        }


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

