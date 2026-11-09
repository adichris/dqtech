"""Paystack hosted checkout adapter. Credentials are scoped to a seller connection."""
import json
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
from urllib.parse import quote,urlparse
class GatewayError(Exception):pass
class Paystack:
    base='https://api.paystack.co'
    def __init__(self,secret):self.secret=secret
    def call(self,method,path,payload=None,many=False):
        request=Request(self.base+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Authorization':'Bearer '+self.secret,'Content-Type':'application/json'},method=method)
        try:
            with urlopen(request,timeout=20) as response:result=json.load(response)
        except (URLError,HTTPError,ValueError):raise GatewayError('The payment provider is unavailable. Check your orders before retrying.') from None
        if not result.get('status') or not isinstance(result.get('data'),list if many else dict):raise GatewayError(str(result.get('message') or 'The provider did not accept this request.')[:200])
        return result['data']
    def initialize(self,email,amount,currency,reference,callback,subaccount='',platform_charge=None):
        payload={'email':email,'amount':int(amount*100),'currency':currency,'reference':reference,'callback_url':callback}
        if subaccount:
            # Split payment: the seller's subaccount receives the payment minus our flat commission;
            # the subaccount bears Paystack's fees.
            payload.update(subaccount=subaccount,bearer='subaccount',transaction_charge=int((platform_charge or 0)*100))
        data=self.call('POST','/transaction/initialize',payload)
        url=data.get('authorization_url','');host=urlparse(url).hostname or ''
        if urlparse(url).scheme!='https' or not (host=='checkout.paystack.com' or host.endswith('.paystack.com')):raise GatewayError('The provider returned an invalid checkout URL.')
        return url
    def verify(self,reference):return self.call('GET','/transaction/verify/'+quote(reference,safe=''))
    def banks(self,currency):
        """Settlement banks and mobile-money providers available for a currency."""
        rows=self.call('GET','/bank?currency='+quote(currency,safe='')+'&perPage=200',many=True)
        return [{'code':str(row.get('code','')),'name':str(row.get('name','')),'type':str(row.get('type',''))} for row in rows if row.get('code') and row.get('active',True) and not row.get('is_deleted')]
    def save_subaccount(self,code,business_name,bank,account_number,email=''):
        payload={'business_name':business_name,'settlement_bank':bank,'account_number':account_number,'percentage_charge':0}
        if email:payload['primary_contact_email']=email
        if code:return self.call('PUT','/subaccount/'+quote(code,safe=''),payload)
        return self.call('POST','/subaccount',payload)
