"""Production entrypoint: existing growth gateway plus rank/price monitor."""

from growth_action_gateway import app  # noqa: F401
import rank_price_gateway  # noqa: F401,E402
