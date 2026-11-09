import unittest,json,hmac,hashlib
from decimal import Decimal
from unittest.mock import patch
from cryptography.fernet import Fernet,InvalidToken
from mall.gateway_crypto import encrypt_secret,decrypt_secret,valid_signature,matches_payment
from mall.paystack import Paystack,GatewayError
class GatewaySecurityTests(unittest.TestCase):
    def setUp(self):
        self.key=Fernet.generate_key();self.secret='sk_test_example_secret_12345';self.body=b'{"event":"charge.success"}'
    def test_secret_encrypted_and_roundtrips(self):
        value=encrypt_secret(self.secret,self.key)
        self.assertNotIn(self.secret,value);self.assertEqual(decrypt_secret(value,self.key),self.secret)
    def test_wrong_key_cannot_decrypt(self):
        with self.assertRaises(InvalidToken):decrypt_secret(encrypt_secret(self.secret,self.key),Fernet.generate_key())
    def test_correct_signature(self):
        sig=hmac.new(self.secret.encode(),self.body,hashlib.sha512).hexdigest()
        self.assertTrue(valid_signature(self.body,sig,self.secret))
    def test_other_tenant_signature_rejected(self):
        sig=hmac.new(b'other_seller_key',self.body,hashlib.sha512).hexdigest()
        self.assertFalse(valid_signature(self.body,sig,self.secret))
    def test_tampered_event_rejected(self):
        sig=hmac.new(self.secret.encode(),self.body,hashlib.sha512).hexdigest()
        self.assertFalse(valid_signature(self.body+b' ',sig,self.secret))
    def test_missing_signature_rejected(self):self.assertFalse(valid_signature(self.body,'',self.secret))
    def data(self):return {'status':'success','reference':'dq_123','amount':12345,'currency':'GHS','id':124}
    def test_exact_payment_matches(self):self.assertTrue(matches_payment(self.data(),'dq_123',Decimal('123.45'),'GHS'))
    def test_wrong_amount_rejected(self):self.assertFalse(matches_payment(self.data(),'dq_123',Decimal('123.46'),'GHS'))
    def test_wrong_currency_rejected(self):self.assertFalse(matches_payment(self.data(),'dq_123',Decimal('123.45'),'NGN'))
    def test_wrong_reference_rejected(self):self.assertFalse(matches_payment(self.data(),'dq_124',Decimal('123.45'),'GHS'))
    def test_pending_payment_rejected(self):
        data=self.data();data['status']='pending';self.assertFalse(matches_payment(data,'dq_123',Decimal('123.45'),'GHS'))
    def test_bool_amount_rejected(self):
        data=self.data();data['amount']=True;self.assertFalse(matches_payment(data,'dq_123',Decimal('.01'),'GHS'))
    def test_evil_provider_redirect_rejected(self):
        with patch.object(Paystack,'call',return_value={'authorization_url':'https://checkout.paystack.com.evil.test/pay'}):
            with self.assertRaises(GatewayError):Paystack(self.secret).initialize('a@example.com',Decimal('10'),'GHS','ref','https://example.com/callback')
    def test_http_redirect_rejected(self):
        with patch.object(Paystack,'call',return_value={'authorization_url':'http://checkout.paystack.com/pay'}):
            with self.assertRaises(GatewayError):Paystack(self.secret).initialize('a@example.com',Decimal('10'),'GHS','ref','https://example.com/callback')
    def test_valid_provider_redirect(self):
        url='https://checkout.paystack.com/example'
        with patch.object(Paystack,'call',return_value={'authorization_url':url}):self.assertEqual(Paystack(self.secret).initialize('a@example.com',Decimal('10'),'GHS','ref','https://example.com/callback'),url)
if __name__=='__main__':unittest.main()
