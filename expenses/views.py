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
    ).order_by('-date', '-created_at')
    
    # Filtry
    transaction_type_filter = request.GET.get('type', '')
    if transaction_type_filter:
        transactions = transactions.filter(transaction_type=transaction_type_filter)
    
    category_filter = request.GET.get('category', '')
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)
    
    # Statistiky
    income = transactions.filter(transaction_type=TransactionType.INCOME).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    expenses = transactions.filter(transaction_type=TransactionType.EXPENSE).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Přesuny (investice) - součet transakcí typu INVESTMENT
    investments = transactions.filter(transaction_type=TransactionType.INVESTMENT).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    net_income = income - expenses
    
    # Poslední transakce (limit 20)
    recent_transactions = transactions[:20]
    
    categories = Category.objects.all()
    
    context = {
        'transactions': recent_transactions,
        'income': income,
        'expenses': expenses,
        'investments': investments,
        'net_income': net_income,
        'period': period,
        'period_label': period_label,
        'categories': categories,
        'transaction_type_filter': transaction_type_filter,
        'category_filter': category_filter,
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
        form = TransactionForm(instance=transaction)
    
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
    """Predikce a očekávané výdaje"""
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    
    # Průměrné příjmy a výdaje z posledních 3 měsíců
    three_months_ago = current_month_start - timedelta(days=90)
    recent_transactions = Transaction.objects.filter(
        date__gte=three_months_ago,
        approved=True
    )
    
    total_income = recent_transactions.filter(transaction_type=TransactionType.INCOME).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    avg_income = total_income / 3  # Průměr za měsíc
    
    total_expenses = recent_transactions.filter(transaction_type=TransactionType.EXPENSE).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    avg_expenses = total_expenses / 3  # Průměr za měsíc
    
    # Očekávané výdaje z trvalých plateb
    recurring_payments = RecurringPayment.objects.filter(active=True)
    expected_recurring = sum([rp.amount for rp in recurring_payments if rp.next_payment_date <= current_month_start + timedelta(days=30)])
    
    # Celkové očekávané výdaje
    expected_expenses = avg_expenses + expected_recurring
    
    # Kontrola limitů
    budget_warnings = []
    for limit in BudgetLimit.objects.filter(active=True):
        month_expenses = Transaction.objects.filter(
            category=limit.category,
            transaction_type=TransactionType.EXPENSE,
            date__gte=current_month_start,
            date__lte=today,
            approved=True
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        if month_expenses > limit.monthly_limit:
            budget_warnings.append({
                'category': limit.category,
                'limit': limit.monthly_limit,
                'current': month_expenses,
                'exceeded': month_expenses - limit.monthly_limit
            })
        elif limit.warning_threshold and month_expenses > limit.warning_threshold:
            budget_warnings.append({
                'category': limit.category,
                'limit': limit.monthly_limit,
                'current': month_expenses,
                'exceeded': None,
                'warning': True
            })
    
    context = {
        'expected_income': avg_income,
        'expected_expenses': expected_expenses,
        'avg_expenses': avg_expenses,
        'expected_recurring': expected_recurring,
        'recurring_payments': recurring_payments,
        'budget_warnings': budget_warnings,
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
        
        # 2. Transakce, které odpovídají podle detailů (kategorie, subkategorie, částka)
        # ale nejsou propojené přes recurring_payment (pro případ, že byly vytvořeny ručně)
        matching_transactions = Transaction.objects.filter(
            category=payment.category,
            subcategory=payment.subcategory,
            amount=payment.amount,
            transaction_type=TransactionType.EXPENSE
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
              transaction_type=TransactionType.EXPENSE)
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
        transaction_type=TransactionType.EXPENSE
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
                transaction_type=TransactionType.EXPENSE
            ).exists()
            
            if duplicate_check:
                messages.warning(request, f'Transakce s těmito údaji již existuje a nemůže být vytvořena znovu.')
                return redirect('recurring_payments')
            
            # Vytvořit novou transakci
            transaction = Transaction.objects.create(
                amount=recurring_payment.amount,
                description=recurring_payment.name,
                transaction_type=TransactionType.EXPENSE,
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

