"""Runtime catalog for active rank/price competitors.

Keeps the SERP and Google-Hotels modules on the same active property list without
requiring duplicate manual edits in both modules.
"""

from __future__ import annotations

import competitor_hotel_prices
import competitor_serp


SERP_COMPETITORS = [
    {"name": "Goldene Wachau - Privatzimmer", "aliases": ["goldene wachau"]},
    {"name": "Haus Gerstbauer", "aliases": ["haus gerstbauer", "ferienwohnung gerstbauer"]},
    {"name": "Ferienwohnung Alte Post - Wachau", "aliases": ["alte post wachau", "ferienwohnung alte post", "alte post aggsbach"]},
    {"name": "Gästehaus Pumi", "aliases": ["gästehaus pumi", "gaestehaus pumi", "wachaupumi"]},
    {"name": "Gasthof zur Venus", "aliases": ["gasthof zur venus", "gasthaus zur venus"]},
    {"name": "Haus Birgit", "aliases": ["haus birgit aggsbach", "haus birgit wachau"]},
    {"name": "Haus Donaublick", "aliases": ["haus donaublick aggsbach", "haus donaublick wachau"]},
    {"name": "M-Haus", "aliases": ["m-haus aggsbach", "m haus aggsbach"]},
    {"name": "Villa Venus", "aliases": ["villa venus willendorf", "villa venus wachau"]},
    {
        "name": "Donauhaus - Natur",
        "aliases": [
            "donauhaus natur",
            "donauhaus",
            "natur kultur entspannung sport",
            "donauhaus aggsbach markt",
        ],
    },
]

HOTEL_COMPETITORS = [
    ("Goldene Wachau - Privatzimmer", ["goldene wachau", "privatzimmer goldene wachau"]),
    ("Haus Gerstbauer", ["haus gerstbauer", "gerstbauer"]),
    ("Ferienwohnung Alte Post - Wachau", ["ferienwohnung alte post", "alte post wachau"]),
    ("Gästehaus Pumi", ["gästehaus pumi", "gaestehaus pumi", "pumi"]),
    ("Gasthof zur Venus", ["gasthof zur venus", "zur venus"]),
    ("Haus Birgit", ["haus birgit"]),
    ("Haus Donaublick", ["haus donaublick", "donaublick"]),
    ("M-Haus", ["m-haus", "m haus"]),
    ("Villa Venus", ["villa venus"]),
    (
        "Donauhaus - Natur",
        [
            "donauhaus natur",
            "donauhaus",
            "natur kultur entspannung sport",
            "donauhaus aggsbach markt",
        ],
    ),
]

# Replace, rather than append, so closed/outdated competitors cannot leak back
# into either rank or price results from the older module constants.
competitor_serp.COMPETITORS[:] = SERP_COMPETITORS
competitor_hotel_prices.COMPETITORS[:] = HOTEL_COMPETITORS
