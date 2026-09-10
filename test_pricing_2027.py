from datetime import date

from pricing_2027 import nightly_direct_rate, stay_room_total


def test_weak_weekday_floor():
    assert nightly_direct_rate(date(2027, 1, 4)) == 99.0


def test_low_season_weekend():
    assert nightly_direct_rate(date(2027, 1, 8)) == 109.0


def test_wine_spring_override():
    assert nightly_direct_rate(date(2027, 5, 1)) == 139.0


def test_wachau_solstice_peak():
    assert nightly_direct_rate(date(2027, 6, 19)) == 149.0


def test_nibelungengau_solstice():
    assert nightly_direct_rate(date(2027, 6, 26)) == 139.0


def test_schallaburg_christmas_market():
    assert nightly_direct_rate(date(2027, 12, 18)) == 129.0


def test_mixed_stay_sums_nightly_rates():
    assert stay_room_total(date(2027, 4, 29), date(2027, 5, 2)) == 397.0


def test_outside_2027_falls_back():
    assert nightly_direct_rate(date(2028, 1, 1)) is None
