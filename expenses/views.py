from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, Count, Avg
from django.utils import timezone
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal
import statistics
import plotly.graph_objects as go
import plotly.express as px
from plotly.offline import plot

from .models import (
    Transaction, Category, Subcategory, RecurringPayment,
    Investment, BudgetLimit, TransactionType, PaymentFor
)
from .forms import TransactionForm, CategoryForm, SubcategoryForm, InvestmentForm, InvestmentValueForm, RecurringPaymentForm


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
    
    # Filtrování transakcí
    transactions = Transaction.objects.filter(
        date__gte=start_date,
        date__lte=end_date
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
    }
    
    return render(request, 'expenses/dashboard.html', context)


@login_required
def add_transaction(request):
    """Přidání nové transakce"""
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.created_by = request.user
            transaction.save()
            messages.success(request, 'Transakce byla úspěšně přidána.')
            return redirect('dashboard')
    else:
        form = TransactionForm(initial={'created_by': request.user})
    
    return render(request, 'expenses/add_transaction.html', {'form': form})


@login_required
def edit_transaction(request, pk):
    """Editace transakce"""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transakce byla úspěšně upravena.')
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
    return redirect('dashboard')


@login_required
def statistics(request):
    """Dlouhodobé statistiky s grafy"""
    # Filtry
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    category_filter = request.GET.get('category', '')
    
    transactions = Transaction.objects.all()
    
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
    
    # Očekávané hodnoty z trvalých plateb pro aktuální měsíc
    recurring_payments = RecurringPayment.objects.filter(active=True)
    expected_income = Decimal('0')
    expected_expenses = Decimal('0')
    expected_income_user1 = Decimal('0')
    expected_income_user2 = Decimal('0')
    expected_expenses_user1 = Decimal('0')
    expected_expenses_user2 = Decimal('0')
    expected_recurring_list = []
    
    for rp in recurring_payments:
        # Použít typ transakce přímo z trvalé platby
        transaction_type = rp.transaction_type
        
        # Zkontrolovat, zda by tato trvalá platba měla proběhnout v aktuálním měsíci
        # Zkontrolovat, zda next_payment_date je v aktuálním měsíci
        # NEBO zda už proběhla v aktuálním měsíci (existuje transakce s datem v aktuálním měsíci)
        payment_date = rp.next_payment_date
        should_occur_this_month = current_month_start <= payment_date <= current_month_end
        
        # Pokud next_payment_date není v aktuálním měsíci, zkontrolovat, zda už proběhla
        if not should_occur_this_month:
            # Zkontrolovat, zda existuje transakce pro tuto trvalou platbu v aktuálním měsíci
            has_transaction_this_month = Transaction.objects.filter(
                recurring_payment=rp,
                date__gte=current_month_start,
                date__lte=current_month_end
            ).exists()
            
            # Nebo zkontrolovat podle detailů (kategorie, subkategorie, částka, typ)
            if not has_transaction_this_month and rp.category:
                has_transaction_this_month = Transaction.objects.filter(
                    category=rp.category,
                    subcategory=rp.subcategory,
                    amount=rp.amount,
                    transaction_type=rp.transaction_type,
                    date__gte=current_month_start,
                    date__lte=current_month_end
                ).exists()
            
            should_occur_this_month = has_transaction_this_month
        
        if should_occur_this_month:
            amount = rp.amount
            if transaction_type == TransactionType.INCOME:
                expected_income += amount
                # Split based on payment_for
                if rp.payment_for == PaymentFor.SELF:
                    expected_income_user1 += amount
                elif rp.payment_for == PaymentFor.PARTNER:
                    expected_income_user2 += amount
                elif rp.payment_for == PaymentFor.SHARED:
                    expected_income_user1 += amount / 2
                    expected_income_user2 += amount / 2
            elif transaction_type == TransactionType.EXPENSE:
                expected_expenses += amount
                # Split based on payment_for
                if rp.payment_for == PaymentFor.SELF:
                    expected_expenses_user1 += amount
                elif rp.payment_for == PaymentFor.PARTNER:
                    expected_expenses_user2 += amount
                elif rp.payment_for == PaymentFor.SHARED:
                    expected_expenses_user1 += amount / 2
                    expected_expenses_user2 += amount / 2
            
            expected_recurring_list.append({
                'payment': rp,
                'type': transaction_type,
                'amount': rp.amount
            })
    
    # Skutečné hodnoty pro aktuální měsíc - pouze pro trvalé platby
    # Najít všechny transakce, které odpovídají trvalým platbám z expected_recurring_list
    actual_income_transaction_ids = []
    actual_expense_transaction_ids = []
    
    for item in expected_recurring_list:
        rp = item['payment']
        transaction_type = item['type']
        
        # Najít transakce pro tuto trvalou platbu v aktuálním měsíci
        # 1. Transakce přímo propojené přes recurring_payment
        matching_transactions = Transaction.objects.filter(
            recurring_payment=rp,
            date__gte=current_month_start,
            date__lte=today,
            transaction_type=transaction_type
        )
        
        # 2. Transakce, které odpovídají podle detailů (kategorie, subkategorie, částka, typ)
        if rp.category:
            matching_by_details = Transaction.objects.filter(
                category=rp.category,
                subcategory=rp.subcategory,
                amount=rp.amount,
                transaction_type=transaction_type,
                date__gte=current_month_start,
                date__lte=today
            ).exclude(id__in=[t.id for t in matching_transactions])
            
            matching_transactions = list(matching_transactions) + list(matching_by_details)
        
        # Přidat do příslušného seznamu podle typu
        for trans in matching_transactions:
            if transaction_type == TransactionType.INCOME:
                if trans.id not in actual_income_transaction_ids:
                    actual_income_transaction_ids.append(trans.id)
            elif transaction_type == TransactionType.EXPENSE:
                if trans.id not in actual_expense_transaction_ids:
                    actual_expense_transaction_ids.append(trans.id)
    
    # Vytvořit querysety z nalezených transakcí
    if actual_income_transaction_ids:
        actual_income_transactions = Transaction.objects.filter(id__in=actual_income_transaction_ids)
    else:
        actual_income_transactions = Transaction.objects.none()
    
    if actual_expense_transaction_ids:
        actual_expense_transactions = Transaction.objects.filter(id__in=actual_expense_transaction_ids)
    else:
        actual_expense_transactions = Transaction.objects.none()
    
    actual_income = actual_income_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    actual_expenses = actual_expense_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    # Calculate split amounts for actual values
    actual_income_user1, actual_income_user2 = calculate_split_amounts(actual_income_transactions)
    actual_expenses_user1, actual_expenses_user2 = calculate_split_amounts(actual_expense_transactions)
    
    # Název aktuálního měsíce
    month_names = {
        1: 'Leden', 2: 'Únor', 3: 'Březen', 4: 'Duben',
        5: 'Květen', 6: 'Červen', 7: 'Červenec', 8: 'Srpen',
        9: 'Září', 10: 'Říjen', 11: 'Listopad', 12: 'Prosinec'
    }
    current_month_name = month_names.get(today.month, '')
    
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
    }
    
    return render(request, 'expenses/predictions.html', context)


@login_required
def recurring_payments(request):
    """Seznam trvalých plateb"""
    today = timezone.now().date()
    next_30_days = today + timedelta(days=30)
    
    payments = RecurringPayment.objects.all().order_by('next_payment_date')
    
    # Rozdělit na nadcházející (next 30 days) a potvrzené (již vytvořené)
    # Zobrazit VŠECHNY platby - historické i budoucí
    upcoming_payments = []
    confirmed_payments = []
    historical_payments = []
    
    for payment in payments:
        # Najít VŠECHNY transakce pro tuto trvalou platbu
        # 1. Transakce přímo propojené přes recurring_payment
        linked_transactions = Transaction.objects.filter(
            recurring_payment=payment
        ).order_by('-date')
        
        # 2. Transakce, které odpovídají podle detailů (kategorie, subkategorie, částka, typ)
        # ale nejsou propojené přes recurring_payment (pro případ, že byly vytvořeny ručně)
        matching_transactions = Transaction.objects.filter(
            category=payment.category,
            subcategory=payment.subcategory,
            amount=payment.amount,
            transaction_type=payment.transaction_type
        ).filter(
            Q(recurring_payment__isnull=True) | Q(recurring_payment=payment)
        ).exclude(
            id__in=linked_transactions.values_list('id', flat=True)
        ).order_by('-date')
        
        # Kombinovat a seřadit podle data, odstranit duplikáty podle ID
        all_confirmed_transactions = list(linked_transactions)
        seen_ids = {t.id for t in all_confirmed_transactions}
        for t in matching_transactions:
            if t.id not in seen_ids:
                all_confirmed_transactions.append(t)
                seen_ids.add(t.id)
        
        all_confirmed_transactions.sort(key=lambda x: x.date, reverse=True)
        
        # Zkontrolovat, zda existuje transakce pro aktuální next_payment_date
        has_current_transaction = Transaction.objects.filter(
            Q(recurring_payment=payment, date=payment.next_payment_date) |
            Q(category=payment.category, subcategory=payment.subcategory, 
              amount=payment.amount, date=payment.next_payment_date,
              transaction_type=payment.transaction_type)
        ).exists()
        
        is_upcoming = payment.next_payment_date <= next_30_days and payment.next_payment_date >= today
        is_past = payment.next_payment_date < today
        
        # Přidat všechny potvrzené transakce do seznamu
        for transaction in all_confirmed_transactions:
            confirmed_payments.append({
                'payment': payment,
                'transaction': transaction,
                'transaction_date': transaction.date,
                'month': transaction.date.strftime('%Y-%m')
            })
        
        # Pokud není potvrzená a je v příštích 30 dnech, přidat do nadcházejících
        if not has_current_transaction and is_upcoming:
            upcoming_payments.append({
                'payment': payment,
                'has_transaction': False,
                'month': payment.next_payment_date.strftime('%Y-%m')
            })
        # Pokud není potvrzená a je v minulosti, přidat do historických
        elif not has_current_transaction and is_past:
            historical_payments.append({
                'payment': payment,
                'has_transaction': False,
                'month': payment.next_payment_date.strftime('%Y-%m')
            })
    
    if request.method == 'POST':
        form = RecurringPaymentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Trvalá platba byla přidána.')
            return redirect('recurring_payments')
    else:
        form = RecurringPaymentForm()
    
    return render(request, 'expenses/recurring_payments.html', {
        'upcoming_payments': upcoming_payments,
        'confirmed_payments': confirmed_payments,
        'historical_payments': historical_payments,
        'form': form
    })


@login_required
def create_transaction_from_recurring(request, pk):
    """Vytvoření transakce z trvalé platby"""
    recurring_payment = get_object_or_404(RecurringPayment, pk=pk)
    
    # Zkontrolovat, zda už existuje transakce pro tuto trvalou platbu a datum
    existing_by_recurring = Transaction.objects.filter(
        recurring_payment=recurring_payment,
        date=recurring_payment.next_payment_date
    ).first()
    
    # Zkontrolovat také podle category, subcategory, amount a date (pro duplikáty)
    # Toto je hlavní kontrola - pokud existuje transakce s těmito údaji, nelze vytvořit novou
    existing_by_details = Transaction.objects.filter(
        category=recurring_payment.category,
        subcategory=recurring_payment.subcategory,
        amount=recurring_payment.amount,
        date=recurring_payment.next_payment_date,
        transaction_type=recurring_payment.transaction_type
    ).first()
    
    # Použít první nalezenou transakci
    existing_transaction = existing_by_recurring or existing_by_details
    
    # Pokud existuje duplikát podle detailů (ne jen podle recurring_payment), nelze vytvořit
    if existing_by_details and not existing_by_recurring:
        messages.warning(request, f'Transakce s těmito údaji (kategorie, subkategorie, částka, datum) již existuje a nemůže být vytvořena znovu.')
        return redirect('recurring_payments')
    
    if request.method == 'POST':
        if existing_transaction:
            # Pokud existuje a uživatel potvrdil přepsání
            if request.POST.get('overwrite') == 'yes':
                # Aktualizovat existující transakci
                existing_transaction.amount = recurring_payment.amount
                existing_transaction.description = recurring_payment.name
                existing_transaction.transaction_type = recurring_payment.transaction_type
                existing_transaction.category = recurring_payment.category
                existing_transaction.subcategory = recurring_payment.subcategory
                existing_transaction.payment_for = recurring_payment.payment_for
                existing_transaction.note = recurring_payment.note
                existing_transaction.save()
                messages.success(request, f'Transakce "{recurring_payment.name}" byla aktualizována.')
            else:
                messages.info(request, 'Transakce nebyla vytvořena.')
                return redirect('recurring_payments')
        else:
            # Zkontrolovat znovu před vytvořením (pro případ, že by někdo mezitím vytvořil)
            duplicate_check = Transaction.objects.filter(
                category=recurring_payment.category,
                subcategory=recurring_payment.subcategory,
                amount=recurring_payment.amount,
                date=recurring_payment.next_payment_date,
                transaction_type=recurring_payment.transaction_type
            ).exists()
            
            if duplicate_check:
                messages.warning(request, f'Transakce s těmito údaji již existuje a nemůže být vytvořena znovu.')
                return redirect('recurring_payments')
            
            # Vytvořit novou transakci
            transaction = Transaction.objects.create(
                amount=recurring_payment.amount,
                description=recurring_payment.name,
                transaction_type=recurring_payment.transaction_type,
                category=recurring_payment.category,
                subcategory=recurring_payment.subcategory,
                date=recurring_payment.next_payment_date,
                payment_for=recurring_payment.payment_for,
                note=recurring_payment.note,
                created_by=request.user,
                recurring_payment=recurring_payment,
                approved=False
            )
            messages.success(request, f'Transakce "{recurring_payment.name}" byla vytvořena.')
        
        # Aktualizovat datum další platby - přidat měsíce pouze pokud bude v příštích 30 dnech
        today = timezone.now().date()
        next_30_days = today + timedelta(days=30)
        
        payment_date = recurring_payment.next_payment_date
        year = payment_date.year
        month = payment_date.month + recurring_payment.frequency_months
        day = payment_date.day
        
        # Zpracovat přetečení měsíců
        while month > 12:
            month -= 12
            year += 1
        
        # Zkontrolovat, zda den existuje v novém měsíci (např. 31. ledna -> 31. února neexistuje)
        from calendar import monthrange
        max_day = monthrange(year, month)[1]
        if day > max_day:
            day = max_day
        
        from datetime import date
        new_payment_date = date(year, month, day)
        
        # Aktualizovat pouze pokud nové datum je v příštích 30 dnech
        if new_payment_date <= next_30_days:
            recurring_payment.next_payment_date = new_payment_date
            recurring_payment.save()
        # Pokud nové datum je mimo 30 dní, ponechat původní datum (nebude se zobrazovat v seznamu)
        
        return redirect('recurring_payments')
    
    # GET request - zobrazit potvrzení
    context = {
        'recurring_payment': recurring_payment,
        'existing_transaction': existing_transaction,
    }
    return render(request, 'expenses/confirm_recurring_transaction.html', context)


@login_required
def investments(request):
    """Přehled investičních skupin"""
    investments_list = Investment.objects.all().order_by('-created_at')
    
    # Vypočítat celkové hodnoty z property metod
    total_invested = sum([inv.invested_amount for inv in investments_list])
    total_current = sum([inv.observed_value or Decimal('0') for inv in investments_list])
    total_profit_loss = total_current - total_invested
    
    # Get all investment transactions to calculate split
    investment_transactions = Transaction.objects.filter(
        transaction_type=TransactionType.INVESTMENT
    )
    total_invested_user1, total_invested_user2 = calculate_split_amounts(investment_transactions)
    
    # Split total_current and total_profit_loss proportionally based on invested amounts
    if total_invested > 0:
        user1_ratio = total_invested_user1 / total_invested
        user2_ratio = total_invested_user2 / total_invested
    else:
        user1_ratio = Decimal('0.5')
        user2_ratio = Decimal('0.5')
    
    total_current_user1 = total_current * user1_ratio
    total_current_user2 = total_current * user2_ratio
    total_profit_loss_user1 = total_profit_loss * user1_ratio
    total_profit_loss_user2 = total_profit_loss * user2_ratio
    
    if request.method == 'POST':
        if 'add_investment' in request.POST:
            form = InvestmentForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Investiční skupina byla přidána.')
                return redirect('investments')
        else:
            form = InvestmentForm()
    else:
        form = InvestmentForm()
    
    context = {
        'investments': investments_list,
        'form': form,
        'total_invested': total_invested,
        'total_current': total_current,
        'total_profit_loss': total_profit_loss,
        'total_invested_user1': total_invested_user1,
        'total_invested_user2': total_invested_user2,
        'total_current_user1': total_current_user1,
        'total_current_user2': total_current_user2,
        'total_profit_loss_user1': total_profit_loss_user1,
        'total_profit_loss_user2': total_profit_loss_user2,
    }
    
    return render(request, 'expenses/investments.html', context)


@login_required
def edit_investment(request, pk):
    """Editace investiční skupiny - název, poznámka a pozorovaná hodnota"""
    investment = get_object_or_404(Investment, pk=pk)
    
    if request.method == 'POST':
        if 'update_value' in request.POST:
            # Aktualizace pouze pozorované hodnoty
            value_form = InvestmentValueForm(request.POST, instance=investment)
            if value_form.is_valid():
                value_form.save()
                messages.success(request, 'Pozorovaná hodnota byla aktualizována.')
                return redirect('investments')
        else:
            # Aktualizace názvu a poznámky
            form = InvestmentForm(request.POST, instance=investment)
            if form.is_valid():
                form.save()
                messages.success(request, 'Investiční skupina byla upravena.')
                return redirect('investments')
    else:
        form = InvestmentForm(instance=investment)
        value_form = InvestmentValueForm(instance=investment)
    
    # Získat transakce spojené s touto investicí
    investment_transactions = investment.transactions.filter(transaction_type=TransactionType.INVESTMENT).order_by('-date')
    
    return render(request, 'expenses/edit_investment.html', {
        'form': form, 
        'value_form': value_form,
        'investment': investment,
        'investment_transactions': investment_transactions,
    })


@login_required
def settings(request):
    """Nastavení - kategorie a subkategorie"""
    categories = Category.objects.all()
    subcategories = Subcategory.objects.all()
    
    # Hledání anomálií
    anomalies = []
    
    # Příliš vysoké položky (nad 3x průměr kategorie)
    for category in categories:
        category_transactions = Transaction.objects.filter(category=category, approved=True)
        if category_transactions.exists():
            avg_amount = category_transactions.aggregate(avg=Sum('amount'))['avg'] / category_transactions.count()
            high_transactions = category_transactions.filter(amount__gt=avg_amount * 3)
            for trans in high_transactions:
                anomalies.append({
                    'type': 'high_amount',
                    'transaction': trans,
                    'category': category,
                    'avg': avg_amount,
                })
    
    # Neodpovídající částky pro kategorii (statisticky odlehlé hodnoty)
    for category in categories:
        category_transactions = Transaction.objects.filter(category=category, approved=True)
        if category_transactions.count() > 5:
            amounts = [float(t.amount) for t in category_transactions]
            if amounts:
                mean = statistics.mean(amounts)
                stdev = statistics.stdev(amounts) if len(amounts) > 1 else 0
                if stdev > 0:
                    for trans in category_transactions:
                        z_score = abs((float(trans.amount) - mean) / stdev) if stdev > 0 else 0
                        if z_score > 3:  # 3 sigma rule
                            anomalies.append({
                                'type': 'outlier',
                                'transaction': trans,
                                'category': category,
                                'z_score': z_score,
                            })
    
    if request.method == 'POST':
        if 'add_category' in request.POST:
            form = CategoryForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Kategorie byla přidána.')
                return redirect('settings')
        elif 'add_subcategory' in request.POST:
            form = SubcategoryForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Subkategorie byla přidána.')
                return redirect('settings')
    else:
        category_form = CategoryForm()
        subcategory_form = SubcategoryForm()
    
    context = {
        'categories': categories,
        'subcategories': subcategories,
        'category_form': CategoryForm(),
        'subcategory_form': SubcategoryForm(),
        'anomalies': anomalies[:20],  # Limit na 20 anomálií
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

