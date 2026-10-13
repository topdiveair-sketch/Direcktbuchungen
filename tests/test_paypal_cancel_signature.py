import ast
from pathlib import Path


def test_cancel_signature_present():
    source = Path('paypal_checkout.py').read_text(encoding='utf-8')
    ast.parse(source)
    assert 'hmac.compare_digest(supplied_signature, cancel_signature(booking_id))' in source
    assert 'sig={cancel_signature(booking_id)}' in source
    assert 'COALESCE(paid,0)=0' in source
