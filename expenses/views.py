import os
import re
import subprocess

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Q, Min, Max
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta, date
from decimal import Decimal
import plotly.graph_objects as go
from plotly.offline import plot
import csv
import io
import json
from collections import defaultdict

from .models import (
    Transaction, Category, Subcategory, RecurringPayment, RecurringPaymentPaidDate,
    Investment, InvestmentObservation, BudgetLimit, TransactionType, PaymentFor
)
from .forms import TransactionForm, CategoryForm, SubcategoryForm, InvestmentForm, InvestmentValueForm, RecurringPaymentForm
from .utils import (
    recurring_list_occurrence_buckets,
    occurrence_matches_series,
    first_day_next_calendar_month,
    first_occurrence_in_month,
    has_occurrence_in_month,
)


def _first_env_value(names):
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _git_short_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _git_commit_date_iso():
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%cI", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


@require_http_methods(["GET"])
def health(_request):
    # Prefer deployment-provided values, then fall back to local git metadata.
    version = _first_env_value(
        [
            "APP_VERSION",
            "RELEASE_VERSION",
            "FLY_IMAGE_REF",
            "FLY_RELEASE_ID",
            "GITHUB_REF_NAME",
            "GITHUB_RUN_NUMBER",
        ]
    )
    commit = _first_env_value(
        [
            "APP_COMMIT",
            "COMMIT_SHA",
            "GIT_COMMIT",
            "SOURCE_COMMIT",
            "GITHUB_SHA",
        ]
    )
    if not commit:
        commit = _git_short_commit()
    commit_date = _first_env_value(["APP_COMMIT_DATE", "COMMIT_DATE", "GITHUB_EVENT_HEAD_COMMIT_TIMESTAMP"])
    if not commit_date:
        commit_date = _git_commit_date_iso()

    fly_info = {
        "app": _first_env_value(["FLY_APP_NAME"]),
        "region": _first_env_value(["FLY_REGION"]),
        "machine_id": _first_env_value(["FLY_MACHINE_ID"]),
        "instance_id": _first_env_value(["FLY_ALLOC_ID"]),
        "release_id": _first_env_value(["FLY_RELEASE_ID"]),
        "image_ref": _first_env_value(["FLY_IMAGE_REF"]),
    }

    return JsonResponse(
        {
            "status": "ok",
            "timestamp": timezone.now().isoformat(),
            "version": version,
            "commit": commit,
            "commit_date": commit_date,
            "fly": fly_info,
        }
    )


def calculate_split_amounts(transactions):
    """Calculate amounts split between user 1 (SELF) and user 2 (PARTNER).
    SHARED transactions are split 50/50.
    Returns: (user1_amount, user2_amount)
    """
    user1_total = Decimal('0')
    user2_total = Decimal('0')
    
    for transaction in transactions:
        amount = transaction.amount
        if transaction.payment_for == PaymentFor.SELF:
            user1_total += amount
        elif transaction.payment_for == PaymentFor.PARTNER:
            user2_total += amount
        elif transaction.payment_for == PaymentFor.SHARED:
            # Split 50/50
            half = amount / 2
            user1_total += half
            user2_total += half
    
    return user1_total, user2_total


def get_split_user_labels():
    """Display labels for the SELF/PARTNER split cards."""
    preferred_order = ['jirka', 'zuzka']
    usernames = list(
        User.objects.filter(username__in=preferred_order)
        .order_by('id')
        .values_list('username', flat=True)
    )
    ordered = [name for name in preferred_order if name in usernames]
    if len(ordered) < 2:
        fallback = list(
            User.objects.exclude(username='admin')
            .order_by('id')
            .values_list('username', flat=True)[:2]
        )
        ordered = fallback if len(fallback) == 2 else ['jirka', 'zuzka']
    return ordered[0], ordered[1]


def payment_for_badge_class(username):
    """Stejné třídy jako u investic (owner-badge-*)."""
    if not username:
        return 'owner-badge-default'
    un = username.lower()
    if un == 'zuzka':
        return 'owner-badge-zuzka'
    if un == 'jirka':
        return 'owner-badge-jirka'
    return 'owner-badge-default'


@login_required
def dashboard(request):
    """Měsíční dashboard"""
    # Toggle mezi kalendářním měsícem a posledními 30 dny
    period = request.GET.get('period', 'month')  # 'month' or '30days'
    
    today = timezone.now().date()
    
    if period == '30days':
        start_date = today - timedelta(days=30)
        end_date = today
        period_label = "Posledních 30 dní"
    else:
        start_date = today.replace(day=1)
        end_date = today
        period_label = f"{today.strftime('%B %Y')}"
    
    # Filtrování transakcí (exclude deleted)
    transactions = Transaction.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        is_deleted=False
    )
    
    # Filtry
    transaction_type_filter = request.GET.get('type', '')
    if transaction_type_filter:
        transactions = transactions.filter(transaction_type=transaction_type_filter)
    
    category_filter = request.GET.get('category', '')
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)
    
    # Řazení
    sort_by = request.GET.get('sort', 'date')
    sort_order = request.GET.get('order', 'desc')
    
    # Mapování názvů sloupců na pole modelu
    sort_fields = {
        'date': 'date',
        'description': 'description',
        'type': 'transaction_type',
        'category': 'category__name',
        'amount': 'amount',
        'created_by': 'created_by__username',
        'created_at': 'created_at',
        'payment_for': 'payment_for',
        'approved': 'approved',
    }
    
    # Výchozí řazení
    if sort_by not in sort_fields:
        sort_by = 'date'
    
    order_field = sort_fields[sort_by]
    
    # Aplikovat řazení
    if sort_order == 'asc':
        transactions = transactions.order_by(order_field, '-created_at')
    else:
        transactions = transactions.order_by(f'-{order_field}', '-created_at')
    
    # Statistiky (před limitováním)
    income_transactions = transactions.filter(transaction_type=TransactionType.INCOME)
    expense_transactions = transactions.filter(transaction_type=TransactionType.EXPENSE)
    investment_transactions = transactions.filter(transaction_type=TransactionType.INVESTMENT)
    
    income = income_transactions.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    expenses = expense_transactions.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Přesuny (investice) - součet transakcí typu INVESTMENT
    investments = investment_transactions.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    net_income = income - expenses
    
    # Calculate split amounts
    income_user1, income_user2 = calculate_split_amounts(income_transactions)
    expenses_user1, expenses_user2 = calculate_split_amounts(expense_transactions)
    investments_user1, investments_user2 = calculate_split_amounts(investment_transactions)
    net_income_user1 = income_user1 - expenses_user1
    net_income_user2 = income_user2 - expenses_user2
    
    # Poslední transakce (limit 20)
    recent_transactions = transactions[:20]
    
    categories = Category.objects.all()
    
    split_user1_label, split_user2_label = get_split_user_labels()

    context = {
        'transactions': recent_transactions,
        'income': income,
        'expenses': expenses,
        'investments': investments,
        'net_income': net_income,
        'income_user1': income_user1,
        'income_user2': income_user2,
        'expenses_user1': expenses_user1,
        'expenses_user2': expenses_user2,
        'investments_user1': investments_user1,
        'investments_user2': investments_user2,
        'net_income_user1': net_income_user1,
        'net_income_user2': net_income_user2,
        'period': period,
        'period_label': period_label,
        'categories': categories,
        'transaction_type_filter': transaction_type_filter,
        'category_filter': category_filter,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'split_user1_label': split_user1_label,
        'split_user2_label': split_user2_label,
    }
    
    return render(request, 'expenses/dashboard.html', context)


@login_required
def manage_transactions(request):
    """Správa transakcí - Přidat a Spravuj."""
    # Handle adding new transaction
    if request.method == 'POST' and 'add_transaction' in request.POST:
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.created_by = request.user
            transaction.approved = False
            transaction.save()
            messages.success(request, 'Transakce byla úspěšně přidána.')
            return redirect(reverse('manage_transactions') + '?tab=manage')
    else:
        form = TransactionForm(
            initial={
                'created_by': request.user,
                'date': timezone.now().date().strftime('%Y-%m-%d'),
            }
        )
    
    # Get all transactions for "Spravuj transakce" section (exclude deleted)
    transactions = Transaction.objects.filter(is_deleted=False)
    
    # Get min and max dates from all transactions for default filter values
    date_range = Transaction.objects.aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    
    # Filters
    transaction_type_filter = request.GET.get('type', '')
    if transaction_type_filter:
        transactions = transactions.filter(transaction_type=transaction_type_filter)
    
    category_filter = request.GET.get('category', '')
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)
    
    # Date filters - use GET params if provided, otherwise use defaults
    date_from = request.GET.get('date_from', '')
    if not date_from and date_range['min_date']:
        date_from = date_range['min_date'].strftime('%Y-%m-%d')
    
    if date_from:
        transactions = transactions.filter(date__gte=date_from)
    
    date_to = request.GET.get('date_to', '')
    if not date_to and date_range['max_date']:
        date_to = date_range['max_date'].strftime('%Y-%m-%d')
    
    if date_to:
        transactions = transactions.filter(date__lte=date_to)
    
    approved_filter = request.GET.get('approved', '')
    if approved_filter == 'yes':
        transactions = transactions.filter(approved=True)
    elif approved_filter == 'no':
        transactions = transactions.filter(approved=False)
    
    # Sorting
    sort_by = request.GET.get('sort', 'date')
    sort_order = request.GET.get('order', 'desc')
    
    sort_fields = {
        'date': 'date',
        'description': 'description',
        'type': 'transaction_type',
        'category': 'category__name',
        'amount': 'amount',
        'created_by': 'created_by__username',
        'created_at': 'created_at',
        'payment_for': 'payment_for',
        'approved': 'approved',
    }
    
    if sort_by not in sort_fields:
        sort_by = 'date'
    
    order_field = sort_fields[sort_by]
    
    if sort_order == 'asc':
        transactions = transactions.order_by(order_field, '-created_at')
    else:
        transactions = transactions.order_by(f'-{order_field}', '-created_at')
    
    categories = Category.objects.all()
    
    # Get min and max dates for export form
    date_range = Transaction.objects.filter(is_deleted=False).aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    
    context = {
        'form': form,
        'transactions': transactions,
        'categories': categories,
        'transaction_type_filter': transaction_type_filter,
        'category_filter': category_filter,
        'date_from': date_from,
        'date_to': date_to,
        'approved_filter': approved_filter,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'date_range': date_range,
    }
    
    return render(request, 'expenses/manage_transactions.html', context)


@login_required
def add_transaction(request):
    """Přidání nové transakce - redirect to manage_transactions"""
    return redirect('manage_transactions')


@login_required
def edit_transaction(request, pk):
    """Editace transakce"""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transakce byla úspěšně upravena.')
            # Redirect back to the page that called this (dashboard or manage_transactions)
            referer = request.META.get('HTTP_REFERER', '')
            if 'manage-transactions' in referer:
                return redirect(reverse('manage_transactions') + '?tab=manage')
            else:
                return redirect('dashboard')
    else:
        # Prefill form with transaction data, ensuring date is set
        form = TransactionForm(instance=transaction)
        # Ensure date is properly formatted for the date input (YYYY-MM-DD format)
        if transaction.date:
            form.initial['date'] = transaction.date.strftime('%Y-%m-%d')
    
    return render(request, 'expenses/edit_transaction.html', {'form': form, 'transaction': transaction})


@login_required
def approve_transaction(request, pk):
    """Schválení transakce"""
    transaction = get_object_or_404(Transaction, pk=pk)
    transaction.approved = True
    transaction.save()
    messages.success(request, 'Transakce byla schválena.')
    # Redirect back to the page that called this (dashboard or manage_transactions)
    referer = request.META.get('HTTP_REFERER', '')
    if 'manage-transactions' in referer:
        return redirect(reverse('manage_transactions') + '?tab=manage')
    else:
        return redirect('dashboard')


@login_required
def statistics(request):
    """Dlouhodobé statistiky s grafy"""
    # Filtry
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    category_filter = request.GET.get('category', '')
    
    transactions = Transaction.objects.filter(is_deleted=False)
    
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)
    
    # Měsíční statistiky
    monthly_stats = transactions.values('date__year', 'date__month').annotate(
        income=Sum('amount', filter=Q(transaction_type=TransactionType.INCOME)),
        expenses=Sum('amount', filter=Q(transaction_type=TransactionType.EXPENSE)),
        investments=Sum('amount', filter=Q(transaction_type=TransactionType.INVESTMENT)),
    ).order_by('date__year', 'date__month')
    
    # Příprava dat pro graf
    months = []
    incomes = []
    expenses_list = []
    net_incomes = []
    investments_list = []
    
    for stat in monthly_stats:
        month_str = f"{stat['date__year']}-{stat['date__month']:02d}"
        months.append(month_str)
        income = stat['income'] or Decimal('0')
        expense = stat['expenses'] or Decimal('0')
        investment = stat['investments'] or Decimal('0')
        incomes.append(float(income))
        expenses_list.append(float(expense))
        net_incomes.append(float(income - expense))
        investments_list.append(float(investment))
    
    # Graf měsíčních statistik
    fig_monthly = go.Figure()
    if months:  # Only add traces if there's data
        fig_monthly.add_trace(go.Scatter(x=months, y=incomes, name='Příjmy', mode='lines+markers', line=dict(color='green')))
        fig_monthly.add_trace(go.Scatter(x=months, y=expenses_list, name='Výdaje', mode='lines+markers', line=dict(color='red')))
        fig_monthly.add_trace(go.Scatter(x=months, y=net_incomes, name='Čistý příjem', mode='lines+markers', line=dict(color='blue')))
        fig_monthly.add_trace(go.Scatter(x=months, y=investments_list, name='Investice', mode='lines+markers', line=dict(color='orange')))
    fig_monthly.update_layout(
        title='Měsíční přehled - Příjmy, Výdaje, Čistý příjem, Investice',
        xaxis_title='Měsíc',
        yaxis_title='Částka (Kč)',
        hovermode='x unified'
    )
    plot_monthly = plot(fig_monthly, output_type='div', include_plotlyjs='cdn')
    
    # Koláčový graf - kategorie
    view_type = request.GET.get('view', 'category')  # 'category' or 'subcategory'
    
    if view_type == 'subcategory':
        category_stats = transactions.filter(transaction_type=TransactionType.EXPENSE).values(
            'subcategory__name'
        ).annotate(total=Sum('amount')).order_by('-total')[:10]
        labels = [s['subcategory__name'] or 'Bez subkategorie' for s in category_stats]
    else:
        category_stats = transactions.filter(transaction_type=TransactionType.EXPENSE).values(
            'category__name'
        ).annotate(total=Sum('amount')).order_by('-total')[:10]
        labels = [s['category__name'] or 'Bez kategorie' for s in category_stats]
    
    values = [float(s['total']) for s in category_stats]
    
    if labels and values:  # Only create pie chart if there's data
        fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values)])
        fig_pie.update_layout(title='Rozpad výdajů podle kategorií' if view_type == 'category' else 'Rozpad výdajů podle subkategorií')
    else:
        fig_pie = go.Figure()
        fig_pie.add_annotation(text='Žádná data k zobrazení', xref='paper', yref='paper', x=0.5, y=0.5, showarrow=False)
        fig_pie.update_layout(title='Rozpad výdajů podle kategorií' if view_type == 'category' else 'Rozpad výdajů podle subkategorií')
    plot_pie = plot(fig_pie, output_type='div', include_plotlyjs='cdn')
    
    # Celkové čisté jmění
    total_income = transactions.filter(transaction_type=TransactionType.INCOME).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    total_expenses = transactions.filter(transaction_type=TransactionType.EXPENSE).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    total_investments = transactions.filter(transaction_type=TransactionType.INVESTMENT).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Aktuální hodnota investic
    current_investment_value = Investment.objects.aggregate(
        total=Sum('observed_value')
    )['total'] or Decimal('0')
    
    net_worth = total_income - total_expenses - total_investments + current_investment_value
    
    # Graf čistého jmění v čase
    cumulative_net = []
    running_total = Decimal('0')
    for stat in monthly_stats:
        income = stat['income'] or Decimal('0')
        expense = stat['expenses'] or Decimal('0')
        investment = stat['investments'] or Decimal('0')
        running_total += income - expense - investment
        cumulative_net.append(float(running_total))
    
    fig_networth = go.Figure()
    if months and cumulative_net:  # Only add trace if there's data
        fig_networth.add_trace(go.Scatter(x=months, y=cumulative_net, name='Čisté jmění', mode='lines+markers', line=dict(color='purple')))
    fig_networth.update_layout(
        title='Vývoj čistého jmění v čase',
        xaxis_title='Měsíc',
        yaxis_title='Částka (Kč)',
        hovermode='x unified'
    )
    plot_networth = plot(fig_networth, output_type='div', include_plotlyjs='cdn')
    
    categories = Category.objects.all()
    
    context = {
        'plot_monthly': plot_monthly,
        'plot_pie': plot_pie,
        'plot_networth': plot_networth,
        'categories': categories,
        'view_type': view_type,
        'start_date': start_date,
        'end_date': end_date,
        'category_filter': category_filter,
        'net_worth': net_worth,
    }
    
    return render(request, 'expenses/statistics.html', context)


@login_required
def predictions(request):
    """Predikce a očekávané výdaje - aktuální měsíc"""
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    
    # Vypočítat konec aktuálního měsíce
    from calendar import monthrange
    last_day = monthrange(today.year, today.month)[1]
    current_month_end = today.replace(day=last_day)
    
    recurring_qs = RecurringPayment.objects.filter(active=True)
    expected_income = Decimal('0')
    expected_expenses = Decimal('0')
    expected_income_user1 = Decimal('0')
    expected_income_user2 = Decimal('0')
    expected_expenses_user1 = Decimal('0')
    expected_expenses_user2 = Decimal('0')
    expected_recurring_list = []

    for rp in recurring_qs:
        if not has_occurrence_in_month(
            rp.start_date, rp.frequency_months, current_month_start, current_month_end
        ):
            continue
        od = first_occurrence_in_month(
            rp.start_date, rp.frequency_months, current_month_start, current_month_end
        )
        amount = rp.amount
        expected_expenses += amount
        expected_expenses_user1 += amount / 2
        expected_expenses_user2 += amount / 2

        expected_recurring_list.append({
            'payment': rp,
            'amount': rp.amount,
            'occurrence_date': od,
        })

    actual_income_transactions = Transaction.objects.filter(
        date__gte=current_month_start,
        date__lte=today,
        transaction_type=TransactionType.INCOME,
        is_deleted=False,
    )
    actual_expense_transactions = Transaction.objects.filter(
        date__gte=current_month_start,
        date__lte=today,
        transaction_type=TransactionType.EXPENSE,
        is_deleted=False,
    )

    actual_income = actual_income_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    actual_expenses = actual_expense_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    actual_income_user1, actual_income_user2 = calculate_split_amounts(actual_income_transactions)
    actual_expenses_user1, actual_expenses_user2 = calculate_split_amounts(actual_expense_transactions)
    
    # Název aktuálního měsíce
    month_names = {
        1: 'Leden', 2: 'Únor', 3: 'Březen', 4: 'Duben',
        5: 'Květen', 6: 'Červen', 7: 'Červenec', 8: 'Srpen',
        9: 'Září', 10: 'Říjen', 11: 'Listopad', 12: 'Prosinec'
    }
    current_month_name = month_names.get(today.month, '')
    
    split_user1_label, split_user2_label = get_split_user_labels()

    context = {
        'expected_income': expected_income,
        'expected_expenses': expected_expenses,
        'expected_income_user1': expected_income_user1,
        'expected_income_user2': expected_income_user2,
        'expected_expenses_user1': expected_expenses_user1,
        'expected_expenses_user2': expected_expenses_user2,
        'actual_income': actual_income,
        'actual_expenses': actual_expenses,
        'actual_income_user1': actual_income_user1,
        'actual_income_user2': actual_income_user2,
        'actual_expenses_user1': actual_expenses_user1,
        'actual_expenses_user2': actual_expenses_user2,
        'expected_recurring_list': expected_recurring_list,
        'current_month_name': current_month_name,
        'current_year': today.year,
        'today': today,
        'current_month_end': current_month_end,
        'split_user1_label': split_user1_label,
        'split_user2_label': split_user2_label,
        'split_user1_badge_class': payment_for_badge_class(split_user1_label),
        'split_user2_badge_class': payment_for_badge_class(split_user2_label),
    }
    
    return render(request, 'expenses/predictions.html', context)


def _recurring_row_dict(payment, due_date, paid_set):
    pid = payment.id
    return {
        'payment': payment,
        'display_date': due_date,
        'is_paid': (pid, due_date) in paid_set,
    }


@login_required
def recurring_payments(request):
    """Trvalé platby — termíny dopočítané od počátečního data; zaplaceno jen orientačně (bez vazby na transakce)."""
    today = timezone.now().date()

    payments = list(RecurringPayment.objects.filter(active=True).order_by('start_date', 'name'))

    paid_pairs = set(
        RecurringPaymentPaidDate.objects.filter(
            recurring_payment_id__in=[p.id for p in payments]
        ).values_list('recurring_payment_id', 'due_date')
    )

    future_rows = []
    current_rows = []
    past_rows = []

    for payment in payments:
        next_m, cur, pst = recurring_list_occurrence_buckets(
            payment.start_date, payment.frequency_months, today
        )
        for od in next_m:
            future_rows.append(_recurring_row_dict(payment, od, paid_pairs))
        for od in cur:
            current_rows.append(_recurring_row_dict(payment, od, paid_pairs))
        for od in pst:
            past_rows.append(_recurring_row_dict(payment, od, paid_pairs))

    future_rows.sort(key=lambda r: (r['display_date'], r['payment'].id))
    current_rows.sort(key=lambda r: (r['display_date'], r['payment'].id))
    past_rows.sort(key=lambda r: (r['display_date'], r['payment'].id), reverse=True)

    month_names = {
        1: 'Leden', 2: 'Únor', 3: 'Březen', 4: 'Duben',
        5: 'Květen', 6: 'Červen', 7: 'Červenec', 8: 'Srpen',
        9: 'Září', 10: 'Říjen', 11: 'Listopad', 12: 'Prosinec',
    }
    next_ms = first_day_next_calendar_month(today)
    next_month_title = f"{month_names.get(next_ms.month, '')} {next_ms.year}"
    current_month_title = f"{month_names.get(today.month, '')} {today.year}"

    if request.method == 'POST':
        form = RecurringPaymentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Trvalá platba byla přidána.')
            return redirect('recurring_payments')
    else:
        form = RecurringPaymentForm()

    return render(request, 'expenses/recurring_payments.html', {
        'future_rows': future_rows,
        'current_rows': current_rows,
        'past_rows': past_rows,
        'form': form,
        'current_month_title': current_month_title,
        'next_month_title': next_month_title,
        'past_from_year': today.year,
    })


@login_required
@require_POST
def recurring_payment_toggle_paid(request):
    payment_id = request.POST.get('payment_id')
    due_raw = request.POST.get('due_date')
    set_paid = request.POST.get('set_paid')
    payment = get_object_or_404(RecurringPayment, pk=payment_id)
    due_date = parse_date(due_raw) if due_raw else None
    if not due_date:
        return redirect('recurring_payments')
    if not occurrence_matches_series(payment.start_date, payment.frequency_months, due_date):
        return redirect('recurring_payments')
    if set_paid == '1':
        RecurringPaymentPaidDate.objects.get_or_create(
            recurring_payment=payment, due_date=due_date
        )
    elif set_paid == '0':
        RecurringPaymentPaidDate.objects.filter(
            recurring_payment=payment, due_date=due_date
        ).delete()
    else:
        existing = RecurringPaymentPaidDate.objects.filter(
            recurring_payment=payment, due_date=due_date
        ).first()
        if existing:
            existing.delete()
        else:
            RecurringPaymentPaidDate.objects.create(recurring_payment=payment, due_date=due_date)
    return redirect('recurring_payments')


@login_required
def investments(request):
    """Přehled investičních skupin"""
    investments_list = Investment.objects.select_related('owner').all().order_by('-created_at')
    investment_rows = []
    sort_by = request.GET.get('sort', 'name')
    sort_order = request.GET.get('order', 'asc')
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    # Vypočítat celkové hodnoty z nejnovějších pozorování
    total_invested = Decimal('0')
    total_current = Decimal('0')
    split_user1_label, split_user2_label = get_split_user_labels()
    total_invested_user1 = Decimal('0')
    total_invested_user2 = Decimal('0')
    total_current_user1 = Decimal('0')
    total_current_user2 = Decimal('0')

    for inv in investments_list:
        observations = list(inv.observations.all().order_by('-observation_date', '-created_at'))
        latest_observation = observations[0] if observations else None
        current_value = latest_observation.observed_value if latest_observation else (inv.observed_value or Decimal('0'))
        current_value_date = latest_observation.observation_date if latest_observation else inv.observed_value_date
        invested_amount = inv.invested_amount
        profit_loss = current_value - invested_amount if current_value else None
        profit_loss_percent = ((current_value - invested_amount) / invested_amount) * 100 if current_value and invested_amount else None

        total_invested += invested_amount
        total_current += current_value

        # Rozdělení statistik podle vlastníka investiční skupiny.
        # Fallback: pokud owner není vyplněný, použij uživatele, který zapsal
        # nejnovější investiční transakci v dané skupině.
        owner_username = (inv.owner.username if inv.owner else '').lower() if inv.owner else ''
        if not owner_username:
            owner_tx = inv.transactions.filter(
                transaction_type=TransactionType.INVESTMENT
            ).exclude(created_by__isnull=True).order_by('-created_at').first()
            owner_username = (owner_tx.created_by.username or '').lower() if owner_tx and owner_tx.created_by else ''

        if owner_username == split_user1_label.lower():
            total_invested_user1 += invested_amount
            total_current_user1 += current_value
        elif owner_username == split_user2_label.lower():
            total_invested_user2 += invested_amount
            total_current_user2 += current_value

        investment_rows.append({
            'investment': inv,
            'owner_name': inv.owner.username if inv.owner else '',
            'observations': observations,
            'latest_observation': latest_observation,
            'invested_amount': invested_amount,
            'observed_value': current_value if current_value else None,
            'observed_value_date': current_value_date,
            'profit_loss': profit_loss,
            'profit_loss_percent': profit_loss_percent,
            'has_more_observations': len(observations) > 1,
        })

    sort_key_map = {
        'name': lambda row: (row['investment'].name or '').lower(),
        'owner': lambda row: (row['owner_name'] or '').lower(),
        'invested': lambda row: row['invested_amount'] or Decimal('0'),
        'observed': lambda row: row['observed_value'] or Decimal('0'),
        'date': lambda row: row['observed_value_date'] or datetime.min.date(),
        'profit': lambda row: row['profit_loss'] or Decimal('0'),
        'percent': lambda row: row['profit_loss_percent'] or Decimal('0'),
    }
    if sort_by not in sort_key_map:
        sort_by = 'name'
    investment_rows = sorted(
        investment_rows,
        key=sort_key_map[sort_by],
        reverse=(sort_order == 'desc')
    )

    def owner_row_class_from_username(owner_user):
        if not owner_user:
            return ''
        name = (owner_user.username or '').lower()
        if name == 'zuzka':
            return 'owner-zuzka-row'
        if name == 'jirka':
            return 'owner-jirka-row'
        return ''

    for row in investment_rows:
        owner = row['investment'].owner
        row['owner_row_class'] = owner_row_class_from_username(owner)
        row['owner_badge_class'] = (
            'owner-badge-zuzka' if owner and owner.username.lower() == 'zuzka'
            else 'owner-badge-jirka' if owner and owner.username.lower() == 'jirka'
            else 'owner-badge-default'
        )

    total_profit_loss = total_current - total_invested
    total_profit_loss_user1 = total_current_user1 - total_invested_user1
    total_profit_loss_user2 = total_current_user2 - total_invested_user2
    
    context = {
        'investment_rows': investment_rows,
        'total_invested': total_invested,
        'total_current': total_current,
        'total_profit_loss': total_profit_loss,
        'total_invested_user1': total_invested_user1,
        'total_invested_user2': total_invested_user2,
        'total_current_user1': total_current_user1,
        'total_current_user2': total_current_user2,
        'total_profit_loss_user1': total_profit_loss_user1,
        'total_profit_loss_user2': total_profit_loss_user2,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'split_user1_label': split_user1_label,
        'split_user2_label': split_user2_label,
    }
    
    return render(request, 'expenses/investments.html', context)


@login_required
def edit_investment(request, pk):
    """Editace konkrétního záznamu pozorování + přidání nového pozorování."""
    investment = get_object_or_404(Investment, pk=pk)
    latest_observation = investment.observations.order_by('-observation_date', '-created_at').first()
    observation_id = request.GET.get('observation_id') or request.POST.get('observation_id')
    if observation_id:
        observation_to_edit = get_object_or_404(InvestmentObservation, pk=observation_id, investment=investment)
    else:
        observation_to_edit = latest_observation

    def sync_latest_observation_fields(target_investment):
        latest_observation = target_investment.observations.order_by('-observation_date', '-created_at').first()
        if latest_observation:
            target_investment.observed_value = latest_observation.observed_value
            target_investment.observed_value_date = latest_observation.observation_date
        else:
            target_investment.observed_value = None
            target_investment.observed_value_date = None
        target_investment.save(update_fields=['observed_value', 'observed_value_date', 'updated_at'])

    edit_initial = {}
    if observation_to_edit:
        edit_initial['observation_date'] = observation_to_edit.observation_date
    edit_form = InvestmentValueForm(instance=observation_to_edit, initial=edit_initial)
    add_form = InvestmentValueForm(initial={'observation_date': timezone.now().date()})

    if request.method == 'POST':
        if 'update_observation' in request.POST:
            if not observation_to_edit:
                messages.error(request, 'Není vybraný záznam k úpravě.')
                return redirect('edit_investment', pk=investment.pk)
            edit_form = InvestmentValueForm(
                request.POST,
                instance=observation_to_edit,
                initial={'observation_date': observation_to_edit.observation_date}
            )
            if edit_form.is_valid():
                edit_form.save()
                sync_latest_observation_fields(investment)
                messages.success(request, 'Záznam pozorování byl upraven.')
                return redirect(f"{reverse('edit_investment', kwargs={'pk': investment.pk})}?observation_id={observation_to_edit.pk}")
        elif 'add_observation' in request.POST:
            add_form = InvestmentValueForm(request.POST, initial={'observation_date': timezone.now().date()})
            if add_form.is_valid():
                new_observation = add_form.save(commit=False)
                new_observation.investment = investment
                new_observation.save()
                sync_latest_observation_fields(investment)
                messages.success(request, 'Nové pozorování bylo přidáno.')
                return redirect(f"{reverse('edit_investment', kwargs={'pk': investment.pk})}?observation_id={new_observation.pk}")

    return render(request, 'expenses/edit_investment.html', {
        'edit_form': edit_form,
        'add_form': add_form,
        'investment': investment,
        'observation_to_edit': observation_to_edit,
    })


TRANSACTION_IMPORT_SESSION_KEY = "transaction_import_preview"
INVESTMENT_IMPORT_SESSION_KEY = "investment_import_preview"
RECURRING_IMPORT_SESSION_KEY = "recurring_import_preview"


def _safe_json_dumps(data):
    return json.dumps(data, ensure_ascii=False, default=str, indent=2)


def _effective_bulk_choice(bulk, checkbox_on, opposite_map):
    """checkbox_on True = použít hromadnou volbu; False = opačná volba."""
    if checkbox_on:
        return bulk
    return opposite_map[bulk]


def _parse_boolean(value, default=False):
    text = (value or "").strip().lower()
    if text in {"ano", "yes", "true", "1"}:
        return True
    if text in {"ne", "no", "false", "0"}:
        return False
    return default


def _parse_transaction_type(value):
    value_lower = (value or "").strip().lower()
    mapping = {
        "příjem": TransactionType.INCOME,
        "prijem": TransactionType.INCOME,
        "income": TransactionType.INCOME,
        "výdaj": TransactionType.EXPENSE,
        "vydaj": TransactionType.EXPENSE,
        "expense": TransactionType.EXPENSE,
        "investice": TransactionType.INVESTMENT,
        "investice (přesun)": TransactionType.INVESTMENT,
        "investment": TransactionType.INVESTMENT,
    }
    if value in dict(TransactionType.choices):
        return value
    return mapping.get(value_lower, TransactionType.EXPENSE)


def _parse_payment_for(value):
    value_lower = (value or "").strip().lower()
    mapping = {
        "za sebe": PaymentFor.SELF,
        "self": PaymentFor.SELF,
        "za partnera": PaymentFor.PARTNER,
        "partner": PaymentFor.PARTNER,
        "společný účet": PaymentFor.SHARED,
        "spolecny ucet": PaymentFor.SHARED,
        "shared": PaymentFor.SHARED,
    }
    if value in dict(PaymentFor.choices):
        return value
    return mapping.get(value_lower, PaymentFor.SELF)


def _parse_date_or_none(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_decimal_or_none(value):
    if value in [None, ""]:
        return None
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _transaction_duplicate_key(item):
    return (
        str(item.get("date") or ""),
        str(item.get("amount") or ""),
        (item.get("description") or "").strip().lower(),
    )


def _observation_duplicate_key(item):
    return (
        str(item.get("observation_date") or ""),
        str(item.get("observed_value") or ""),
        (item.get("investment_name") or "").strip().lower(),
    )


def _recurring_duplicate_key(item):
    return (
        (item.get("name") or "").strip().lower(),
        str(item.get("start_date") or ""),
        str(item.get("amount") or ""),
        str(item.get("frequency_months") or ""),
    )


def _serialize_transaction_for_json(t):
    return {
        "id": t.id,
        "date": t.date.isoformat() if t.date else "",
        "description": t.description,
        "transaction_type": t.transaction_type,
        "transaction_type_label": t.get_transaction_type_display(),
        "category": t.category.name if t.category else "",
        "subcategory": t.subcategory.name if t.subcategory else "",
        "amount": str(t.amount),
        "payment_for": t.payment_for,
        "payment_for_label": t.get_payment_for_display(),
        "months_duration": t.months_duration,
        "approved": t.approved,
        "note": t.note or "",
        "created_by": t.created_by.username if t.created_by else "",
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "is_imported": t.is_imported,
        "investment_name": t.investment.name if t.investment else "",
    }


def _serialize_observation_for_json(obs):
    return {
        "id": obs.id,
        "investment_name": obs.investment.name,
        "owner": obs.investment.owner.username if obs.investment.owner else "",
        "observed_value": str(obs.observed_value),
        "observation_date": obs.observation_date.isoformat(),
        "investment_note": obs.investment.note or "",
        "created_at": obs.created_at.isoformat() if obs.created_at else "",
    }


def _build_transaction_export_csv_response(transactions, filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "Datum", "Popis", "Typ", "Kategorie", "Subkategorie",
        "Částka (Kč)", "Za koho", "Na kolik měsíců",
        "Schváleno", "Poznámka", "Kdo zapsal", "Datum zapsání", "Importováno", "Investiční skupina"
    ])
    for t in transactions:
        writer.writerow([
            t.date.isoformat() if t.date else "",
            t.description,
            t.get_transaction_type_display(),
            t.category.name if t.category else "",
            t.subcategory.name if t.subcategory else "",
            str(t.amount),
            t.get_payment_for_display(),
            t.months_duration,
            "Ano" if t.approved else "Ne",
            t.note or "",
            t.created_by.username if t.created_by else "",
            t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "",
            "Ano" if t.is_imported else "Ne",
            t.investment.name if t.investment else "",
        ])
    return response


def _build_observation_export_csv_response(observations, filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "Investiční skupina", "Vlastník", "Pozorovaná hodnota", "Datum pozorování", "Poznámka investice", "Vytvořeno"
    ])
    for obs in observations:
        writer.writerow([
            obs.investment.name,
            obs.investment.owner.username if obs.investment.owner else "",
            str(obs.observed_value),
            obs.observation_date.isoformat(),
            obs.investment.note or "",
            obs.created_at.strftime("%Y-%m-%d %H:%M:%S") if obs.created_at else "",
        ])
    return response


def _read_uploaded_rows(file):
    filename = (file.name or "").lower()
    if filename.endswith(".json"):
        payload = json.loads(file.read().decode("utf-8-sig"))
        if isinstance(payload, dict):
            if isinstance(payload.get("items"), list):
                return payload["items"]
            return []
        return payload if isinstance(payload, list) else []
    if filename.endswith(".csv"):
        content = file.read().decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(content)))
    raise ValueError("Nepodporovaný soubor. Použijte CSV nebo JSON.")


def _normalize_transaction_rows(rows, user):
    normalized = []
    errors = []
    for idx, row in enumerate(rows, start=1):
        row_lower = {str(k).strip().lower(): v for k, v in row.items()} if isinstance(row, dict) else {}
        date = _parse_date_or_none(row_lower.get("datum") or row_lower.get("date"))
        amount = _parse_decimal_or_none(row_lower.get("částka (kč)") or row_lower.get("castka (kc)") or row_lower.get("amount"))
        description = (row_lower.get("popis") or row_lower.get("description") or "").strip()
        if not date or amount is None or not description:
            errors.append(f"Řádek {idx}: povinná pole jsou datum, částka a popis.")
            continue
        transaction_type = _parse_transaction_type(row_lower.get("typ") or row_lower.get("transaction_type"))
        category_name = (row_lower.get("kategorie") or row_lower.get("category") or "").strip()
        subcategory_name = (row_lower.get("subkategorie") or row_lower.get("subcategory") or "").strip()
        investment_name = (row_lower.get("investiční skupina") or row_lower.get("investicni skupina") or row_lower.get("investment_name") or "").strip()
        category = Category.objects.filter(name__iexact=category_name).first() if category_name else None
        subcategory = None
        if subcategory_name and category:
            subcategory = Subcategory.objects.filter(category=category, name__iexact=subcategory_name).first()
        investment = Investment.objects.filter(name__iexact=investment_name).first() if investment_name else None
        try:
            months_duration = int(row_lower.get("na kolik měsíců") or row_lower.get("na kolik mesicu") or row_lower.get("months_duration") or 0)
        except Exception:
            months_duration = 0
        normalized.append({
            "date": date.isoformat(),
            "description": description,
            "transaction_type": transaction_type,
            "category_id": category.id if category else None,
            "subcategory_id": subcategory.id if subcategory else None,
            "amount": str(amount),
            "payment_for": _parse_payment_for(row_lower.get("za koho") or row_lower.get("payment_for")),
            "months_duration": months_duration,
            "approved": _parse_boolean(row_lower.get("schváleno") or row_lower.get("schvaleno") or row_lower.get("approved"), default=False),
            "note": (row_lower.get("poznámka") or row_lower.get("poznamka") or row_lower.get("note") or "").strip(),
            "investment_id": investment.id if investment else None,
            "created_by_id": user.id,
            "is_imported": True,
            "is_deleted": False,
        })
    return normalized, errors


def _normalize_observation_rows(rows):
    normalized = []
    errors = []
    for idx, row in enumerate(rows, start=1):
        row_lower = {str(k).strip().lower(): v for k, v in row.items()} if isinstance(row, dict) else {}
        investment_name = (row_lower.get("investiční skupina") or row_lower.get("investicni skupina") or row_lower.get("investment_name") or "").strip()
        observed_value = _parse_decimal_or_none(row_lower.get("pozorovaná hodnota") or row_lower.get("pozorovana hodnota") or row_lower.get("observed_value"))
        observation_date = _parse_date_or_none(row_lower.get("datum pozorování") or row_lower.get("datum pozorovani") or row_lower.get("observation_date"))
        if not investment_name or observed_value is None or not observation_date:
            errors.append(f"Řádek {idx}: povinná pole jsou investiční skupina, pozorovaná hodnota a datum pozorování.")
            continue
        investment = Investment.objects.filter(name__iexact=investment_name).first()
        if not investment:
            errors.append(f"Řádek {idx}: investiční skupina '{investment_name}' neexistuje.")
            continue
        normalized.append({
            "investment_id": investment.id,
            "investment_name": investment.name,
            "observed_value": str(observed_value),
            "observation_date": observation_date.isoformat(),
        })
    return normalized, errors


def _duplicate_preview_split(existing_items, incoming_items, key_builder):
    """Spáruje duplicity podle klíče; zbytek rozdělí na jen-v-databázi vs. jen-v-souboru."""
    existing_by_key = defaultdict(list)
    incoming_by_key = defaultdict(list)
    for item in existing_items:
        existing_by_key[key_builder(item)].append(item)
    for index, item in enumerate(incoming_items):
        incoming_by_key[key_builder(item)].append((index, item))

    duplicate_pairs = []
    only_existing = []
    only_incoming = []

    all_keys = set(existing_by_key.keys()) | set(incoming_by_key.keys())
    for key in all_keys:
        existing_list = existing_by_key.get(key, [])
        incoming_list = incoming_by_key.get(key, [])
        pair_count = min(len(existing_list), len(incoming_list))
        for i in range(pair_count):
            duplicate_pairs.append({
                "incoming_index": incoming_list[i][0],
                "old": existing_list[i],
                "new": incoming_list[i][1],
            })
        for j in range(pair_count, len(existing_list)):
            only_existing.append(existing_list[j])
        for j in range(pair_count, len(incoming_list)):
            only_incoming.append({
                "incoming_index": incoming_list[j][0],
                "new": incoming_list[j][1],
            })

    duplicate_pairs.sort(key=lambda x: x["incoming_index"])
    only_incoming.sort(key=lambda x: x["incoming_index"])
    return duplicate_pairs, only_existing, only_incoming


def _build_transaction_preview(import_mode, new_items):
    existing_qs = Transaction.objects.filter(is_deleted=False).order_by("date", "created_at")
    existing_items = [{
        "id": t.id,
        "date": t.date.isoformat(),
        "description": t.description,
        "amount": str(t.amount),
        "transaction_type": t.transaction_type,
    } for t in existing_qs]
    duplicate_pairs, only_existing, only_incoming = _duplicate_preview_split(
        existing_items, new_items, _transaction_duplicate_key
    )
    return {
        "dataset": "transactions",
        "import_mode": import_mode,
        "existing_count": len(existing_items),
        "file_count": len(new_items),
        "overlap_count": len(duplicate_pairs),
        "duplicate_pairs": duplicate_pairs,
        "only_existing_count": len(only_existing),
        "only_incoming_count": len(only_incoming),
        "only_existing": only_existing,
        "only_incoming": only_incoming,
        "new_items": new_items,
    }


def _build_observation_preview(import_mode, new_items):
    existing_qs = InvestmentObservation.objects.select_related("investment").order_by("observation_date", "created_at")
    existing_items = [{
        "id": obs.id,
        "observation_date": obs.observation_date.isoformat(),
        "observed_value": str(obs.observed_value),
        "investment_name": obs.investment.name,
    } for obs in existing_qs]
    duplicate_pairs, only_existing, only_incoming = _duplicate_preview_split(
        existing_items, new_items, _observation_duplicate_key
    )
    return {
        "dataset": "investment_observations",
        "import_mode": import_mode,
        "existing_count": len(existing_items),
        "file_count": len(new_items),
        "overlap_count": len(duplicate_pairs),
        "duplicate_pairs": duplicate_pairs,
        "only_existing_count": len(only_existing),
        "only_incoming_count": len(only_incoming),
        "only_existing": only_existing,
        "only_incoming": only_incoming,
        "new_items": new_items,
    }


def _serialize_recurring_for_json(rp):
    paid = list(rp.paid_dates.order_by("due_date").values_list("due_date", flat=True))
    return {
        "id": rp.id,
        "name": rp.name,
        "amount": str(rp.amount),
        "frequency_months": rp.frequency_months,
        "start_date": rp.start_date.isoformat(),
        "active": rp.active,
        "paid_dates": [d.isoformat() for d in paid],
    }


def _build_recurring_export_csv_response(recurring_qs, filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "ID", "Název", "Částka (Kč)", "Frekvence (měsíce)", "Počáteční datum",
        "Aktivní", "Uhrazené termíny",
    ])
    for rp in recurring_qs:
        paid = list(rp.paid_dates.order_by("due_date").values_list("due_date", flat=True))
        paid_str = ";".join(d.isoformat() for d in paid)
        writer.writerow([
            rp.id,
            rp.name,
            str(rp.amount),
            rp.frequency_months,
            rp.start_date.isoformat(),
            "Ano" if rp.active else "Ne",
            paid_str,
        ])
    return response


def _parse_paid_dates_cell(value):
    if not value and value != 0:
        return []
    text = str(value).strip()
    if not text:
        return []
    out = []
    for part in re.split(r"[;,]", text):
        part = part.strip()
        if not part:
            continue
        d = _parse_date_or_none(part)
        if d:
            out.append(d.isoformat())
    return out


def _sync_recurring_paid_dates(rp, paid_date_strings):
    rp.paid_dates.all().delete()
    for s in paid_date_strings or []:
        d = _parse_date_or_none(s)
        if not d:
            continue
        if not occurrence_matches_series(rp.start_date, rp.frequency_months, d):
            continue
        RecurringPaymentPaidDate.objects.get_or_create(recurring_payment=rp, due_date=d)


def _normalize_recurring_rows(rows):
    normalized = []
    errors = []
    for idx, row in enumerate(rows, start=1):
        row_lower = {str(k).strip().lower(): v for k, v in row.items()} if isinstance(row, dict) else {}
        name = (row_lower.get("název") or row_lower.get("nazev") or row_lower.get("name") or "").strip()
        amount = _parse_decimal_or_none(
            row_lower.get("částka (kč)") or row_lower.get("castka (kc)") or row_lower.get("amount")
        )
        start_date = _parse_date_or_none(
            row_lower.get("počáteční datum") or row_lower.get("pocatecni datum") or row_lower.get("start_date")
        )
        freq_raw = row_lower.get("frekvence (měsíce)") or row_lower.get("frekvence (mesice)") or row_lower.get("frequency_months")
        try:
            frequency_months = int(freq_raw) if freq_raw not in (None, "") else 1
        except (TypeError, ValueError):
            frequency_months = 1
        if frequency_months < 1:
            frequency_months = 1
        if not name or amount is None or not start_date:
            errors.append(f"Řádek {idx}: povinná pole jsou název, částka a počáteční datum.")
            continue
        paid_raw = row_lower.get("uhrazené termíny") or row_lower.get("uhrazene terminy") or row_lower.get("paid_dates")
        paid_dates = _parse_paid_dates_cell(paid_raw)
        row_id = row_lower.get("id")
        try:
            row_id = int(row_id) if row_id not in (None, "") else None
        except (TypeError, ValueError):
            row_id = None
        normalized.append({
            "id": row_id,
            "name": name,
            "amount": str(amount),
            "frequency_months": frequency_months,
            "start_date": start_date.isoformat(),
            "active": _parse_boolean(row_lower.get("aktivní") or row_lower.get("aktivni") or row_lower.get("active"), default=True),
            "paid_dates": paid_dates,
        })
    return normalized, errors


def _build_recurring_preview(import_mode, new_items):
    existing_qs = RecurringPayment.objects.order_by("start_date", "id")
    existing_items = []
    for rp in existing_qs:
        existing_items.append({
            "id": rp.id,
            "name": rp.name,
            "start_date": rp.start_date.isoformat(),
            "amount": str(rp.amount),
            "frequency_months": rp.frequency_months,
        })
    duplicate_pairs, only_existing, only_incoming = _duplicate_preview_split(
        existing_items, new_items, _recurring_duplicate_key
    )
    return {
        "dataset": "recurring_payments",
        "import_mode": import_mode,
        "existing_count": len(existing_items),
        "file_count": len(new_items),
        "overlap_count": len(duplicate_pairs),
        "duplicate_pairs": duplicate_pairs,
        "only_existing_count": len(only_existing),
        "only_incoming_count": len(only_incoming),
        "only_existing": only_existing,
        "only_incoming": only_incoming,
        "new_items": new_items,
    }


@login_required
def settings(request):
    """Nastavení - kategorie, subkategorie a import/export."""
    categories = Category.objects.prefetch_related('subcategories').all()
    subcategories = Subcategory.objects.select_related('category').all()
    category_form = CategoryForm()
    subcategory_form = SubcategoryForm()
    investment_form = InvestmentForm(initial={'owner': request.user})

    transaction_date_range = Transaction.objects.filter(is_deleted=False).aggregate(
        min_date=Min("date"),
        max_date=Max("date"),
    )
    transaction_preview = request.session.get(TRANSACTION_IMPORT_SESSION_KEY)
    observation_preview = request.session.get(INVESTMENT_IMPORT_SESSION_KEY)
    recurring_preview = request.session.get(RECURRING_IMPORT_SESSION_KEY)

    if request.method == 'POST':
        if 'add_category' in request.POST:
            category_form = CategoryForm(request.POST)
            if category_form.is_valid():
                category_form.save()
                messages.success(request, 'Kategorie byla přidána.')
                return redirect('settings')
        elif 'add_subcategory' in request.POST:
            subcategory_form = SubcategoryForm(request.POST)
            if subcategory_form.is_valid():
                subcategory_form.save()
                messages.success(request, 'Subkategorie byla přidána.')
                return redirect('settings')
        elif 'add_investment' in request.POST:
            investment_form = InvestmentForm(request.POST)
            if investment_form.is_valid():
                investment = investment_form.save(commit=False)
                if not investment.owner:
                    investment.owner = request.user
                investment.save()
                messages.success(request, 'Investiční skupina byla přidána.')
                return redirect('settings')
        
    context = {
        'categories': categories,
        'subcategories': subcategories,
        'category_form': category_form,
        'subcategory_form': subcategory_form,
        'investment_form': investment_form,
        'transaction_date_range': transaction_date_range,
        'transaction_import_preview': transaction_preview,
        'investment_import_preview': observation_preview,
        'recurring_import_preview': recurring_preview,
    }

    return render(request, 'expenses/settings.html', context)


@login_required
def get_subcategories(request):
    """AJAX endpoint pro načtení subkategorií podle kategorie"""
    category_id = request.GET.get('category_id')
    if category_id:
        subcategories = Subcategory.objects.filter(category_id=category_id).values('id', 'name')
        return JsonResponse(list(subcategories), safe=False)
    return JsonResponse([], safe=False)


@login_required
def export_transactions(request):
    """Export transakcí do CSV nebo JSON."""
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    export_format = request.GET.get("format", "csv")
    transactions = Transaction.objects.filter(is_deleted=False).order_by("date", "created_at")
    if date_from:
        transactions = transactions.filter(date__gte=date_from)
    if date_to:
        transactions = transactions.filter(date__lte=date_to)

    filename_base = f"transakce_{date_from or 'all'}_{date_to or 'all'}"
    if export_format == "json":
        payload = {
            "dataset": "transactions",
            "exported_at": timezone.now().isoformat(),
            "count": transactions.count(),
            "items": [_serialize_transaction_for_json(t) for t in transactions],
        }
        response = HttpResponse(_safe_json_dumps(payload), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}.json"'
        return response

    return _build_transaction_export_csv_response(transactions, f"{filename_base}.csv")


@login_required
def import_transactions(request):
    """Dvoufázový import transakcí z CSV/JSON s náhledem duplicit."""
    if request.method != "POST":
        return redirect("settings")

    action = request.POST.get("action", "preview")
    if action == "cancel":
        request.session.pop(TRANSACTION_IMPORT_SESSION_KEY, None)
        messages.info(request, "Náhled importu transakcí byl zrušen.")
        return redirect("settings")

    if action == "preview":
        upload = request.FILES.get("file")
        import_mode = request.POST.get("import_mode", "append")
        if not upload:
            messages.error(request, "Vyberte soubor pro import.")
            return redirect("settings")
        if import_mode not in {"append", "replace"}:
            messages.error(request, "Neplatný režim importu.")
            return redirect("settings")
        try:
            rows = _read_uploaded_rows(upload)
            normalized_rows, errors = _normalize_transaction_rows(rows, request.user)
            if errors:
                messages.error(request, "Import se nepodařilo načíst: " + " | ".join(errors[:6]))
                return redirect("settings")
            preview = _build_transaction_preview(import_mode, normalized_rows)
            request.session[TRANSACTION_IMPORT_SESSION_KEY] = preview
            messages.info(request, "Náhled importu transakcí je připravený. Zkontrolujte překryvy a potvrďte.")
        except Exception as exc:
            messages.error(request, f"Chyba při čtení souboru: {exc}")
        return redirect("settings")

    preview = request.session.get(TRANSACTION_IMPORT_SESSION_KEY)
    if not preview:
        messages.error(request, "Náhled importu vypršel. Nahrajte soubor znovu.")
        return redirect("settings")

    duplicate_pairs = preview.get("duplicate_pairs") or []
    dup_decision = request.POST.get("duplicate_decision", "").strip()
    if duplicate_pairs:
        if dup_decision not in {"old", "new", "both"}:
            messages.error(request, "Vyberte hromadnou volbu pro duplicity: starý, nový, nebo oba.")
            return redirect("settings")

    only_existing_bulk = request.POST.get("only_existing_bulk", "keep")
    if only_existing_bulk not in {"keep", "drop"}:
        only_existing_bulk = "keep"
    only_incoming_bulk = request.POST.get("only_incoming_bulk", "import")
    if only_incoming_bulk not in {"import", "skip"}:
        only_incoming_bulk = "import"

    opp_exist = {"keep": "drop", "drop": "keep"}
    opp_inc = {"import": "skip", "skip": "import"}

    only_existing_keep = {}
    for row in preview.get("only_existing") or []:
        tid = row.get("id")
        if tid is None:
            continue
        cb_on = request.POST.get(f"only_existing_apply_{tid}") == "1"
        eff = _effective_bulk_choice(only_existing_bulk, cb_on, opp_exist)
        only_existing_keep[tid] = eff == "keep"

    only_incoming_import = {}
    for entry in preview.get("only_incoming") or []:
        idx = entry.get("incoming_index")
        if idx is None:
            continue
        cb_on = request.POST.get(f"only_incoming_apply_{idx}") == "1"
        eff = _effective_bulk_choice(only_incoming_bulk, cb_on, opp_inc)
        only_incoming_import[idx] = eff == "import"

    imported_count = 0
    with transaction.atomic():
        if preview["import_mode"] == "replace":
            Transaction.objects.filter(is_deleted=False).update(is_deleted=True)

        for pair in duplicate_pairs:
            decision = dup_decision
            old_id = pair["old"].get("id")
            if old_id:
                if decision == "new":
                    Transaction.objects.filter(pk=old_id).update(is_deleted=True)
                elif decision in {"old", "both"}:
                    Transaction.objects.filter(pk=old_id).update(is_deleted=False)
            if decision in {"new", "both"}:
                new_item = pair["new"]
                Transaction.objects.create(
                    date=_parse_date_or_none(new_item.get("date")),
                    description=new_item.get("description", ""),
                    transaction_type=new_item.get("transaction_type") or TransactionType.EXPENSE,
                    category_id=new_item.get("category_id"),
                    subcategory_id=new_item.get("subcategory_id"),
                    amount=_parse_decimal_or_none(new_item.get("amount")) or Decimal("0"),
                    payment_for=new_item.get("payment_for") or PaymentFor.SELF,
                    months_duration=new_item.get("months_duration") or 0,
                    approved=bool(new_item.get("approved")),
                    note=new_item.get("note") or "",
                    created_by_id=request.user.id,
                    investment_id=new_item.get("investment_id"),
                    is_imported=True,
                    is_deleted=False,
                )
                imported_count += 1

        duplicate_indexes = {pair["incoming_index"] for pair in duplicate_pairs}
        for index, item in enumerate(preview["new_items"]):
            if index in duplicate_indexes:
                continue
            if not only_incoming_import.get(index, True):
                continue
            Transaction.objects.create(
                date=_parse_date_or_none(item.get("date")),
                description=item.get("description", ""),
                transaction_type=item.get("transaction_type") or TransactionType.EXPENSE,
                category_id=item.get("category_id"),
                subcategory_id=item.get("subcategory_id"),
                amount=_parse_decimal_or_none(item.get("amount")) or Decimal("0"),
                payment_for=item.get("payment_for") or PaymentFor.SELF,
                months_duration=item.get("months_duration") or 0,
                approved=bool(item.get("approved")),
                note=item.get("note") or "",
                created_by_id=request.user.id,
                investment_id=item.get("investment_id"),
                is_imported=True,
                is_deleted=False,
            )
            imported_count += 1

        for tid, want_keep in only_existing_keep.items():
            if want_keep:
                Transaction.objects.filter(pk=tid).update(is_deleted=False)
            else:
                Transaction.objects.filter(pk=tid).update(is_deleted=True)

    request.session.pop(TRANSACTION_IMPORT_SESSION_KEY, None)
    messages.success(
        request,
        f"Import transakcí dokončen. Nově zapsáno {imported_count} řádků, překryvy vyřešeny: {len(preview['duplicate_pairs'])}.",
    )
    return redirect("settings")


@login_required
def export_investment_observations(request):
    """Export pozorování investic do CSV nebo JSON."""
    export_format = request.GET.get("format", "csv")
    observations = InvestmentObservation.objects.select_related("investment", "investment__owner").order_by("observation_date", "created_at")
    filename_base = "investice_pozorovani"
    if export_format == "json":
        payload = {
            "dataset": "investment_observations",
            "exported_at": timezone.now().isoformat(),
            "count": observations.count(),
            "items": [_serialize_observation_for_json(obs) for obs in observations],
        }
        response = HttpResponse(_safe_json_dumps(payload), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}.json"'
        return response
    return _build_observation_export_csv_response(observations, f"{filename_base}.csv")


@login_required
def import_investment_observations(request):
    """Dvoufázový import pozorování investic z CSV/JSON s kontrolou duplicit."""
    if request.method != "POST":
        return redirect("settings")

    action = request.POST.get("action", "preview")
    if action == "cancel":
        request.session.pop(INVESTMENT_IMPORT_SESSION_KEY, None)
        messages.info(request, "Náhled importu investičních pozorování byl zrušen.")
        return redirect("settings")

    if action == "preview":
        upload = request.FILES.get("file")
        import_mode = request.POST.get("import_mode", "append")
        if not upload:
            messages.error(request, "Vyberte soubor pro import.")
            return redirect("settings")
        if import_mode not in {"append", "replace"}:
            messages.error(request, "Neplatný režim importu.")
            return redirect("settings")
        try:
            rows = _read_uploaded_rows(upload)
            normalized_rows, errors = _normalize_observation_rows(rows)
            if errors:
                messages.error(request, "Import se nepodařilo načíst: " + " | ".join(errors[:6]))
                return redirect("settings")
            preview = _build_observation_preview(import_mode, normalized_rows)
            request.session[INVESTMENT_IMPORT_SESSION_KEY] = preview
            messages.info(request, "Náhled importu investičních pozorování je připravený.")
        except Exception as exc:
            messages.error(request, f"Chyba při čtení souboru: {exc}")
        return redirect("settings")

    preview = request.session.get(INVESTMENT_IMPORT_SESSION_KEY)
    if not preview:
        messages.error(request, "Náhled importu vypršel. Nahrajte soubor znovu.")
        return redirect("settings")

    duplicate_pairs = preview.get("duplicate_pairs") or []
    dup_decision = request.POST.get("duplicate_decision", "").strip()
    if duplicate_pairs:
        if dup_decision not in {"old", "new", "both"}:
            messages.error(request, "Vyberte hromadnou volbu pro duplicity: starý, nový, nebo oba.")
            return redirect("settings")

    only_existing_bulk = request.POST.get("only_existing_bulk", "keep")
    if only_existing_bulk not in {"keep", "drop"}:
        only_existing_bulk = "keep"
    only_incoming_bulk = request.POST.get("only_incoming_bulk", "import")
    if only_incoming_bulk not in {"import", "skip"}:
        only_incoming_bulk = "import"

    opp_exist = {"keep": "drop", "drop": "keep"}
    opp_inc = {"import": "skip", "skip": "import"}

    only_existing_keep = {}
    for row in preview.get("only_existing") or []:
        oid = row.get("id")
        if oid is None:
            continue
        cb_on = request.POST.get(f"only_existing_apply_{oid}") == "1"
        eff = _effective_bulk_choice(only_existing_bulk, cb_on, opp_exist)
        only_existing_keep[oid] = eff == "keep"

    only_incoming_import = {}
    for entry in preview.get("only_incoming") or []:
        idx = entry.get("incoming_index")
        if idx is None:
            continue
        cb_on = request.POST.get(f"only_incoming_apply_{idx}") == "1"
        eff = _effective_bulk_choice(only_incoming_bulk, cb_on, opp_inc)
        only_incoming_import[idx] = eff == "import"

    imported_count = 0
    with transaction.atomic():
        existing_ids_before = set(InvestmentObservation.objects.values_list("id", flat=True))
        keep_old_ids = set()

        for pair in duplicate_pairs:
            decision = dup_decision
            old_id = pair["old"].get("id")
            if old_id:
                if decision in {"old", "both"}:
                    keep_old_ids.add(old_id)
                if decision == "new":
                    InvestmentObservation.objects.filter(pk=old_id).delete()
            if decision in {"new", "both"}:
                new_item = pair["new"]
                InvestmentObservation.objects.create(
                    investment_id=new_item["investment_id"],
                    observed_value=_parse_decimal_or_none(new_item.get("observed_value")) or Decimal("0"),
                    observation_date=_parse_date_or_none(new_item.get("observation_date")),
                )
                imported_count += 1

        duplicate_indexes = {pair["incoming_index"] for pair in duplicate_pairs}
        for index, item in enumerate(preview["new_items"]):
            if index in duplicate_indexes:
                continue
            if not only_incoming_import.get(index, True):
                continue
            InvestmentObservation.objects.create(
                investment_id=item["investment_id"],
                observed_value=_parse_decimal_or_none(item.get("observed_value")) or Decimal("0"),
                observation_date=_parse_date_or_none(item.get("observation_date")),
            )
            imported_count += 1

        for oid, want_keep in only_existing_keep.items():
            if want_keep:
                keep_old_ids.add(oid)
            else:
                InvestmentObservation.objects.filter(pk=oid).delete()

        if preview["import_mode"] == "replace":
            delete_ids = existing_ids_before - keep_old_ids
            if delete_ids:
                InvestmentObservation.objects.filter(id__in=delete_ids).delete()

        for investment in Investment.objects.all():
            latest = investment.observations.order_by("-observation_date", "-created_at").first()
            if latest:
                investment.observed_value = latest.observed_value
                investment.observed_value_date = latest.observation_date
            else:
                investment.observed_value = None
                investment.observed_value_date = None
            investment.save(update_fields=["observed_value", "observed_value_date", "updated_at"])

    request.session.pop(INVESTMENT_IMPORT_SESSION_KEY, None)
    messages.success(
        request,
        f"Import pozorování investic dokončen. Nově zapsáno {imported_count} řádků, překryvy vyřešeny: {len(preview['duplicate_pairs'])}.",
    )
    return redirect("settings")


def _create_recurring_from_import_item(item):
    rp = RecurringPayment.objects.create(
        name=item["name"].strip(),
        amount=_parse_decimal_or_none(item.get("amount")) or Decimal("0"),
        frequency_months=int(item.get("frequency_months") or 1),
        start_date=_parse_date_or_none(item.get("start_date")),
        active=bool(item.get("active", True)),
    )
    _sync_recurring_paid_dates(rp, item.get("paid_dates") or [])
    return rp


@login_required
def export_recurring_payments(request):
    """Export trvalých plateb (včetně uhrazených termínů) do CSV nebo JSON."""
    export_format = request.GET.get("format", "csv")
    recurring_qs = RecurringPayment.objects.prefetch_related("paid_dates").order_by("start_date", "id")
    filename_base = "trvale_platby"
    if export_format == "json":
        payload = {
            "dataset": "recurring_payments",
            "exported_at": timezone.now().isoformat(),
            "count": recurring_qs.count(),
            "items": [_serialize_recurring_for_json(rp) for rp in recurring_qs],
        }
        response = HttpResponse(_safe_json_dumps(payload), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}.json"'
        return response
    return _build_recurring_export_csv_response(recurring_qs, f"{filename_base}.csv")


@login_required
def import_recurring_payments(request):
    """Dvoufázový import trvalých plateb z CSV/JSON s náhledem duplicit."""
    if request.method != "POST":
        return redirect("settings")

    action = request.POST.get("action", "preview")
    if action == "cancel":
        request.session.pop(RECURRING_IMPORT_SESSION_KEY, None)
        messages.info(request, "Náhled importu trvalých plateb byl zrušen.")
        return redirect("settings")

    if action == "preview":
        upload = request.FILES.get("file")
        import_mode = request.POST.get("import_mode", "append")
        if not upload:
            messages.error(request, "Vyberte soubor pro import.")
            return redirect("settings")
        if import_mode not in {"append", "replace"}:
            messages.error(request, "Neplatný režim importu.")
            return redirect("settings")
        try:
            rows = _read_uploaded_rows(upload)
            normalized_rows, errors = _normalize_recurring_rows(rows)
            if errors:
                messages.error(request, "Import se nepodařilo načíst: " + " | ".join(errors[:6]))
                return redirect("settings")
            preview = _build_recurring_preview(import_mode, normalized_rows)
            request.session[RECURRING_IMPORT_SESSION_KEY] = preview
            messages.info(request, "Náhled importu trvalých plateb je připravený.")
        except Exception as exc:
            messages.error(request, f"Chyba při čtení souboru: {exc}")
        return redirect("settings")

    preview = request.session.get(RECURRING_IMPORT_SESSION_KEY)
    if not preview:
        messages.error(request, "Náhled importu vypršel. Nahrajte soubor znovu.")
        return redirect("settings")

    duplicate_pairs = preview.get("duplicate_pairs") or []
    dup_decision = request.POST.get("duplicate_decision", "").strip()
    if duplicate_pairs:
        if dup_decision not in {"old", "new", "both"}:
            messages.error(request, "Vyberte hromadnou volbu pro duplicity: starý, nový, nebo oba.")
            return redirect("settings")

    only_existing_bulk = request.POST.get("only_existing_bulk", "keep")
    if only_existing_bulk not in {"keep", "drop"}:
        only_existing_bulk = "keep"
    only_incoming_bulk = request.POST.get("only_incoming_bulk", "import")
    if only_incoming_bulk not in {"import", "skip"}:
        only_incoming_bulk = "import"

    opp_exist = {"keep": "drop", "drop": "keep"}
    opp_inc = {"import": "skip", "skip": "import"}

    only_existing_keep = {}
    for row in preview.get("only_existing") or []:
        oid = row.get("id")
        if oid is None:
            continue
        cb_on = request.POST.get(f"only_existing_apply_{oid}") == "1"
        eff = _effective_bulk_choice(only_existing_bulk, cb_on, opp_exist)
        only_existing_keep[oid] = eff == "keep"

    only_incoming_import = {}
    for entry in preview.get("only_incoming") or []:
        idx = entry.get("incoming_index")
        if idx is None:
            continue
        cb_on = request.POST.get(f"only_incoming_apply_{idx}") == "1"
        eff = _effective_bulk_choice(only_incoming_bulk, cb_on, opp_inc)
        only_incoming_import[idx] = eff == "import"

    imported_count = 0
    with transaction.atomic():
        existing_ids_before = set(RecurringPayment.objects.values_list("id", flat=True))
        keep_old_ids = set()

        for pair in duplicate_pairs:
            decision = dup_decision
            old_id = pair["old"].get("id")
            if old_id:
                if decision in {"old", "both"}:
                    keep_old_ids.add(old_id)
                if decision == "new":
                    RecurringPayment.objects.filter(pk=old_id).delete()
            if decision in {"new", "both"}:
                new_item = pair["new"]
                _create_recurring_from_import_item(new_item)
                imported_count += 1

        duplicate_indexes = {pair["incoming_index"] for pair in duplicate_pairs}
        for index, item in enumerate(preview["new_items"]):
            if index in duplicate_indexes:
                continue
            if not only_incoming_import.get(index, True):
                continue
            _create_recurring_from_import_item(item)
            imported_count += 1

        for oid, want_keep in only_existing_keep.items():
            if want_keep:
                keep_old_ids.add(oid)
            else:
                RecurringPayment.objects.filter(pk=oid).delete()

        if preview["import_mode"] == "replace":
            delete_ids = existing_ids_before - keep_old_ids
            if delete_ids:
                RecurringPayment.objects.filter(id__in=delete_ids).delete()

    request.session.pop(RECURRING_IMPORT_SESSION_KEY, None)
    messages.success(
        request,
        f"Import trvalých plateb dokončen. Nově zapsáno {imported_count} záznamů, překryvy vyřešeny: {len(duplicate_pairs)}.",
    )
    return redirect("settings")


@login_required
def download_import_template(request, dataset, template_format):
    """Stažení šablony importu pro transakce, pozorování investic nebo trvalé platby."""
    if dataset not in {"transactions", "investment_observations", "recurring_payments"}:
        messages.error(request, "Neznámý typ šablony.")
        return redirect("settings")
    if template_format not in {"csv", "json"}:
        messages.error(request, "Neznámý formát šablony.")
        return redirect("settings")

    if dataset == "transactions":
        sample = {
            "Datum": "2026-05-01",
            "Popis": "Nákup potravin",
            "Typ": "Výdaj",
            "Kategorie": "Domácnost",
            "Subkategorie": "Potraviny",
            "Částka (Kč)": "1250.00",
            "Za koho": "Společný účet",
            "Na kolik měsíců": "0",
            "Schváleno": "Ano",
            "Poznámka": "Týdenní nákup",
            "Investiční skupina": "",
        }
        filename_base = "template_import_transakce"
    elif dataset == "investment_observations":
        sample = {
            "Investiční skupina": "S&P 500 ETF",
            "Pozorovaná hodnota": "154320.50",
            "Datum pozorování": "2026-05-01",
        }
        filename_base = "template_import_investice_pozorovani"
    else:
        sample = {
            "ID": "",
            "Název": "Nájem",
            "Částka (Kč)": "12000.00",
            "Frekvence (měsíce)": "1",
            "Počáteční datum": "2026-01-05",
            "Aktivní": "Ano",
            "Uhrazené termíny": "2026-05-05",
        }
        filename_base = "template_import_trvale_platby"

    if template_format == "json":
        payload = {"dataset": dataset, "items": [sample]}
        response = HttpResponse(_safe_json_dumps(payload), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}.json"'
        return response

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename_base}.csv"'
    response.write("\ufeff")
    writer = csv.DictWriter(response, fieldnames=list(sample.keys()))
    writer.writeheader()
    writer.writerow(sample)
    return response


@login_required
def remove_transaction(request, pk):
    """Soft delete transakce (pouze pro importované)"""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    if not transaction.is_imported:
        messages.error(request, 'Lze odstranit pouze importované transakce.')
        return redirect('manage_transactions?tab=manage')
    
    if request.method == 'POST':
        transaction.is_deleted = True
        transaction.save()
        messages.success(request, 'Transakce byla odstraněna.')
        return redirect('manage_transactions?tab=manage')
    
    # GET request - show confirmation
    return render(request, 'expenses/confirm_remove_transaction.html', {'transaction': transaction})

