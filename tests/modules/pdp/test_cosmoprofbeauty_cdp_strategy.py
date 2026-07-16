from __future__ import annotations

from modules.pdp.cosmoprofbeauty_cdp_strategy import CosmoprofbeautyCDPStrategy


def test_cosmoprofbeauty_strategy_uses_name_anchor_selector() -> None:
    strategy = CosmoprofbeautyCDPStrategy()

    assert ".pdp-link__name" in strategy.selector
    assert ".grid-tile a[href$='.html']" not in strategy.selector
