import pandas as pd
import pytest

from alphalab.shadow import ShadowBook


def test_shadow_nav_tracks_held_weights(tmp_path, prices):
    book = ShadowBook(path=tmp_path / "s.json", starting_nav=1000.0)
    d0, d1 = prices.index[0], prices.index[1]

    book.mark("mom", d0.date(), {"AAA": 1.0}, prices)
    book.mark("mom", d1.date(), {"AAA": 1.0}, prices)

    expected = 1000.0 * float(prices.loc[d1, "AAA"] / prices.loc[d0, "AAA"])
    assert book.nav_by_sleeve["mom"][d1.date().isoformat()] == pytest.approx(expected)


def test_shadow_book_round_trips_to_disk(tmp_path, prices):
    path = tmp_path / "s.json"
    book = ShadowBook(path=path)
    book.mark("mom", prices.index[0].date(), {"AAA": 1.0}, prices)
    book.save()
    assert ShadowBook.load(path).nav_by_sleeve == book.nav_by_sleeve


def test_scorecard_requires_enough_history(tmp_path, prices):
    book = ShadowBook(path=tmp_path / "s.json")
    book.mark("mom", prices.index[0].date(), {"AAA": 1.0}, prices)
    assert book.scorecard("mom", 4.25) is None
