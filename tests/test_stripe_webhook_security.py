import hashlib
import hmac
import pytest
from stripe_webhook_security import verify_stripe_signature, StripeSignatureError


def test_signature_validation():
    secret = 'test-secret'
    body = b'test-payload'
    timestamp = 1791900000
    signature = hmac.new(secret.encode(), str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
    header = f't={timestamp},v1={signature}'
    verify_stripe_signature(body, header, secret, now=timestamp)
    for changed_body, changed_time in [(b'changed', timestamp), (body, timestamp + 301)]:
        with pytest.raises(StripeSignatureError):
            verify_stripe_signature(changed_body, header, secret, now=changed_time)
