"""Obecné pomůcky pro výpočty nad daty."""
from calendar import monthrange
from datetime import date


def add_calendar_months(d: date, months: int) -> date:
    """Přičte měsíce k datu s ohledem na konec měsíce (např. 31.1 + 1 měsíc = 28/29.2)."""
    if months == 0:
        return d
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    max_day = monthrange(y, m)[1]
    day = min(d.day, max_day)
    return date(y, m, day)


def end_of_month(d: date) -> date:
    last = monthrange(d.year, d.month)[1]
    return d.replace(day=last)


def first_day_next_calendar_month(today: date) -> date:
    """První den kalendářního měsíce následujícího po měsíci data ``today``."""
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def recurring_list_occurrence_buckets(start: date, frequency_months: int, today: date):
    """
    Termíny série do tří sekcí UI:
    - next_month: jen naplánovaný **následující kalendářní měsíc** (např. červen, je-li teď květen),
    - current: aktuální kalendářní měsíc,
    - past: od 1. 1. běžného roku do konce měsíce před aktuálním (starší než letošní rok se neukazují).
    Termíny za horizontem „příští měsíc“ se nevykreslují (objeví se až posune kalendář).
    """
    if frequency_months < 1:
        frequency_months = 1

    year_floor = date(today.year, 1, 1)
    month_start = today.replace(day=1)
    month_end = end_of_month(today)
    next_ms = first_day_next_calendar_month(today)
    next_me = end_of_month(next_ms)

    next_month, current, past = [], [], []
    k = 0
    while k < 2000:
        od = add_calendar_months(start, k * frequency_months)
        if od < year_floor:
            k += 1
            continue
        if od < month_start:
            past.append(od)
        elif od <= month_end:
            current.append(od)
        elif next_ms <= od <= next_me:
            next_month.append(od)
        # výskyty až za „příštím měsícem“ přeskočíme (zobrazí se později), série pokračuje
        k += 1

    next_month.sort()
    current.sort()
    past.sort(reverse=True)
    return next_month, current, past


def occurrence_matches_series(start: date, frequency_months: int, candidate: date) -> bool:
    """Je datum přesně jedním z termínů série od start_date?"""
    if frequency_months < 1:
        frequency_months = 1
    k = 0
    while k < 2000:
        od = add_calendar_months(start, k * frequency_months)
        if od == candidate:
            return True
        if od > candidate:
            return False
        k += 1
    return False


def first_occurrence_in_month(start: date, frequency_months: int, month_start: date, month_end: date):
    """První termín série spadající do [month_start, month_end], nebo None."""
    if frequency_months < 1:
        frequency_months = 1
    k = 0
    while k < 2000:
        od = add_calendar_months(start, k * frequency_months)
        if od > month_end:
            return None
        if od >= month_start:
            return od
        k += 1
    return None


def has_occurrence_in_month(start: date, frequency_months: int, month_start: date, month_end: date) -> bool:
    return first_occurrence_in_month(start, frequency_months, month_start, month_end) is not None
