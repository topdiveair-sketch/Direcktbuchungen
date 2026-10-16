"""Read-only Stripe sandbox Checkout Session retrieval for reconciliation.

Never infer payment status from browser redirects. Only the Stripe API
response is suitable for checking whether an unpaid hold can be released.
"""
import json
import urllib.error
import urllib.parse
import urllib.request


class StripeSessionLookupError(RuntimeError):
    pass


def retrieve_test_checkout_session(*, secret_key: str, session_id: str,
                                   timeout: int = 20, opener=None) -> dict:
    if not secret_key or not secret_key.startswith("sk_test_"):
        raise StripeSessionLookupError("Sandbox credentials required")
    if not session_id or not session_id.startswith("cs_test_"):
        raise StripeSessionLookupError("Invalid sandbox session identifier")
    if len(session_id) > 255 or not all(c.isalnum() or c in "_-" for c in session_id):
        raise StripeSessionLookupError("Invalid session identifier characters")
    url = "https://api.stripe.com/v1/checkout/sessions/" + urllib.parse.quote(session_id, safe="")
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + secret_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            session = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
        raise StripeSessionLookupError("Stripe session lookup failed") from exc
    if not isinstance(session, dict) or session.get("id") != session_id or session.get("livemode") is not False:
        raise StripeSessionLookupError("Stripe returned a mismatched or live session")
    return session
