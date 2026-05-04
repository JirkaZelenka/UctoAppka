from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    Category, Subcategory, Transaction, RecurringPayment, RecurringPaymentPaidDate,
    Investment, Institution, BudgetLimit
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'created_at']
    list_filter = ['type']
    search_fields = ['name']


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'created_at']
    list_filter = ['category']
    search_fields = ['name', 'category__name']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'transaction_type', 'category', 'investment', 'institution', 'date', 'created_by', 'approved']
    list_filter = ['transaction_type', 'category', 'approved', 'date', 'payment_for', 'investment', 'institution']
    search_fields = ['description', 'note']
    date_hierarchy = 'date'
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RecurringPayment)
class RecurringPaymentAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'amount', 'frequency_months', 'start_date', 'active', 'permanent']
    list_filter = ['active', 'permanent', 'owner']
    search_fields = ['name']


@admin.register(RecurringPaymentPaidDate)
class RecurringPaymentPaidDateAdmin(admin.ModelAdmin):
    list_display = ['recurring_payment', 'due_date', 'created_at']
    list_filter = ['due_date']
    date_hierarchy = 'due_date'


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'price', 'frequency', 'start_date', 'end_date', 'created_at']
    search_fields = ['name', 'service_description', 'contact']
    list_filter = ['owner']


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

