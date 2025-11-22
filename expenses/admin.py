from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    Category, Subcategory, Transaction, RecurringPayment, 
    Investment, BudgetLimit
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name', 'description']


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'description', 'created_at']
    list_filter = ['category']
    search_fields = ['name', 'description']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'transaction_type', 'category', 'investment', 'date', 'created_by', 'approved']
    list_filter = ['transaction_type', 'category', 'approved', 'date', 'payment_for', 'investment']
    search_fields = ['description', 'note']
    date_hierarchy = 'date'
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RecurringPayment)
class RecurringPaymentAdmin(admin.ModelAdmin):
    list_display = ['name', 'amount', 'frequency_months', 'next_payment_date', 'active']
    list_filter = ['active', 'payment_for']
    search_fields = ['name', 'note']


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'invested_amount', 'observed_value', 'observed_value_date', 'created_at']
    search_fields = ['name', 'note']
    date_hierarchy = 'created_at'
    readonly_fields = ['invested_amount', 'created_at', 'updated_at']


@admin.register(BudgetLimit)
class BudgetLimitAdmin(admin.ModelAdmin):
    list_display = ['category', 'monthly_limit', 'warning_threshold', 'active']
    list_filter = ['active']
    search_fields = ['category__name']

