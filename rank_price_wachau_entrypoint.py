"""WachauEtappe production entrypoint plus rank/price monitors."""

from wachauetappe_gateway import app  # noqa: F401
import competitor_catalog_runtime  # noqa: F401,E402
import rank_price_gateway  # noqa: F401,E402
import rank_price_windows_api  # noqa: F401,E402
