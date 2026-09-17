"""WachauEtappe production entrypoint plus the admin rank/price monitor."""

from wachauetappe_gateway import app  # noqa: F401
import rank_price_gateway  # noqa: F401,E402
