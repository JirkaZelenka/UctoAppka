from django.urls import path
from . import views

urlpatterns = [
    path('health', views.health, name='health'),
    path('health/', views.health),
    path('', views.dashboard, name='dashboard'),
    path('manage-transactions/', views.manage_transactions, name='manage_transactions'),
    path('add-transaction/', views.add_transaction, name='add_transaction'),
    path('edit-transaction/<int:pk>/', views.edit_transaction, name='edit_transaction'),
    path('approve-transaction/<int:pk>/', views.approve_transaction, name='approve_transaction'),
    path('statistics/', views.statistics, name='statistics'),
    path('predictions/', views.predictions, name='predictions'),
    path('recurring-payments/', views.recurring_payments, name='recurring_payments'),
    path('create-transaction-from-recurring/<int:pk>/', views.create_transaction_from_recurring, name='create_transaction_from_recurring'),
    path('investments/', views.investments, name='investments'),
    path('edit-investment/<int:pk>/', views.edit_investment, name='edit_investment'),
    path('settings/', views.settings, name='settings'),
    path('api/subcategories/', views.get_subcategories, name='get_subcategories'),
    path('export-transactions/', views.export_transactions, name='export_transactions'),
    path('import-transactions/', views.import_transactions, name='import_transactions'),
    path('remove-transaction/<int:pk>/', views.remove_transaction, name='remove_transaction'),
]

