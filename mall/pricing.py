from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import calendar

def trial_end(start: date) -> date:
    month = start.month + 3
    year = start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))

def commission(total: Decimal, rate: Decimal, start: date, today: date) -> Decimal:
    if total < 0 or not Decimal('0') <= rate <= Decimal('1'):
        raise ValueError('Invalid sale amount or commission rate.')
    if today < trial_end(start):
        return Decimal('0.00')
    return (total * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
