"""Railway entrypoint that activates the 2027 direct-booking rate calendar."""

# Must run first so railway_app imports the patched price_breakdown function.
import pricing_2027_gateway  # noqa: F401

from projectos_winter_gateway import app  # noqa: E402,F401
