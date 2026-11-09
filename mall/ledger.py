from decimal import Decimal
from django.db import transaction
from .models import Journal,Posting
@transaction.atomic
def post(shop,key,description,entries):
    from .accounting import validate_entries
    entries=validate_entries(entries)
    journal,created=Journal.objects.get_or_create(key=key,defaults={'shop':shop,'description':description})
    if not created:
        if journal.shop_id!=shop.pk:raise ValueError('Journal ownership mismatch.')
        return journal
    Posting.objects.bulk_create([Posting(journal=journal,account=a,debit=d,credit=c) for a,d,c in entries])
    return journal
