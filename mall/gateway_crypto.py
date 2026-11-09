import hashlib
import hmac
from cryptography.fernet import Fernet,InvalidToken

def encrypt_secret(secret,key):
    return Fernet(key.encode() if isinstance(key,str) else key).encrypt(secret.encode()).decode()
def decrypt_secret(value,key):
    return Fernet(key.encode() if isinstance(key,str) else key).decrypt(value.encode()).decode()
def valid_signature(body,signature,secret):
    if not signature or len(signature)!=128:return False
    expected=hmac.new(secret.encode(),body,hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected,signature)
def matches_payment(data,reference,amount,currency):
    from decimal import Decimal
    return (data.get('status')=='success' and data.get('reference')==reference
        and type(data.get('amount')) is int and data['amount']==int(amount*Decimal('100'))
        and data.get('currency')==currency and bool(data.get('id')))
