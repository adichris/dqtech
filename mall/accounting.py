from decimal import Decimal

def validate_entries(entries):
    entries=[(a,Decimal(d),Decimal(c)) for a,d,c in entries]
    if not entries:raise ValueError('A journal needs at least two entries.')
    debit=sum((d for _,d,_ in entries),Decimal('0'))
    credit=sum((c for _,_,c in entries),Decimal('0'))
    if debit!=credit or debit<=0:raise ValueError('A journal must balance and contain a positive amount.')
    if any(not a or d<0 or c<0 or (d>0 and c>0) or d.as_tuple().exponent < -2 or c.as_tuple().exponent < -2 for a,d,c in entries):raise ValueError('Invalid journal posting.')
    return entries
