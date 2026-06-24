"""Tests for gather_prices — live quote fetch + manual-entry fallback.

gather_prices wraps fetch_quotes (TWS) and falls back to interactive
prompting via get_float_input for any asset without a usable quote. It
returns three dicts keyed by asset class:

- prices      — fair-value (midprice) for valuation
- buy_prices  — ask-based, for BUY order sizing
- sell_prices — bid-based, for SELL order sizing

For manually entered prices all three are identical. Tests monkeypatch
fetch_quotes (to avoid TWS) and get_float_input (to avoid blocking on
stdin) and cover: full live fetch, TWS connection failure, partial fetch
with manual fallback, and filtering of unknown symbols.
"""
import pytest

import main
from main import gather_prices


STRATEGY = {"Equity": {}, "Bonds": {}, "Gold": {}}
SYMBOL_MAP = {"SPYY": "Equity", "XGLE": "Bonds", "EWG2": "Gold"}
CONTRACTS = []  # contents irrelevant; fetch_quotes is monkeypatched


def quote(symbol, bid=None, ask=None, last=None, close=None,
          spread_pct=None):
    """Build a quote dict matching ib.fetch_quotes' return shape."""
    return {"symbol": symbol, "bid": bid, "ask": ask, "last": last,
            "close": close, "spread_pct": spread_pct}


# ── Full live fetch ─────────────────────────────────────────────────────

def test_live_fetch_populates_all_three_price_dicts(monkeypatch):
    monkeypatch.setattr(main, "fetch_quotes", lambda contracts: [
        quote("SPYY", bid=100.0, ask=102.0, spread_pct=1.9608),
        quote("XGLE", bid=50.0,  ask=51.0),
        quote("EWG2", bid=120.0, ask=122.0),
    ])
    # Should not prompt for any asset.
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))

    prices, buy, sell = gather_prices(CONTRACTS, SYMBOL_MAP, STRATEGY)

    # Fair-value = midprice.
    assert prices == {"Equity": 101.0, "Bonds": 50.5, "Gold": 121.0}
    # Buy = ask, sell = bid.
    assert buy  == {"Equity": 102.0, "Bonds": 51.0, "Gold": 122.0}
    assert sell == {"Equity": 100.0, "Bonds": 50.0, "Gold": 120.0}


def test_live_fetch_uses_fallback_chain_when_one_side_missing(monkeypatch):
    """bid-only quote: midprice unavailable → resolve_price falls back to bid."""
    monkeypatch.setattr(main, "fetch_quotes", lambda contracts: [
        quote("SPYY", bid=100.0),  # ask is None
        quote("XGLE", bid=50.0, ask=51.0),
        quote("EWG2", bid=120.0, ask=122.0),
    ])
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))

    prices, buy, sell = gather_prices(CONTRACTS, SYMBOL_MAP, STRATEGY)

    # Equity: no ask → buy falls back to fair-value chain (bid), sell = bid.
    assert prices["Equity"] == 100.0
    assert buy["Equity"]  == 100.0   # resolve_buy_price → resolve_price → bid
    assert sell["Equity"] == 100.0


# ── TWS connection failure → full manual fallback ───────────────────────

def test_tws_failure_falls_back_to_manual_entry(monkeypatch, capsys):
    def boom(contracts):
        raise ConnectionError("TWS refused")
    monkeypatch.setattr(main, "fetch_quotes", boom)

    inputs = iter([105.50, 52.20, 121.05])
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: next(inputs))

    prices, buy, sell = gather_prices(CONTRACTS, SYMBOL_MAP, STRATEGY)

    # All three dicts identical for manually entered prices.
    expected = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
    assert prices == expected
    assert buy == expected
    assert sell == expected

    # User is told why manual entry is happening.
    out = capsys.readouterr().out
    assert "TWS connection failed" in out
    assert "Falling back to manual price entry" in out


# ── Partial fetch → manual fallback only for missing assets ─────────────

def test_partial_fetch_prompts_only_for_missing_assets(monkeypatch):
    """TWS returns 2 of 3; the third should be prompted, the others not."""
    monkeypatch.setattr(main, "fetch_quotes", lambda contracts: [
        quote("SPYY", bid=100.0, ask=102.0),
        quote("XGLE", bid=50.0,  ask=51.0),
        # EWG2 / Gold missing
    ])
    prompted = []
    def fake_input(prompt):
        prompted.append(prompt)
        return 121.05
    monkeypatch.setattr(main, "get_float_input", fake_input)

    prices, buy, sell = gather_prices(CONTRACTS, SYMBOL_MAP, STRATEGY)

    # Only Gold was prompted.
    assert len(prompted) == 1
    assert "Gold" in prompted[0]
    # Live-fetched assets use bid/ask; manually entered asset is symmetric.
    assert prices["Gold"] == buy["Gold"] == sell["Gold"] == 121.05
    assert buy["Equity"] == 102.0 and sell["Equity"] == 100.0


# ── Unknown symbols in quotes are skipped ───────────────────────────────

def test_unknown_symbol_in_quotes_is_ignored(monkeypatch):
    """A quote for a symbol not in symbol_map must be silently dropped."""
    monkeypatch.setattr(main, "fetch_quotes", lambda contracts: [
        quote("SPYY", bid=100.0, ask=102.0),
        quote("UNKNOWN_TICKER", bid=1.0, ask=2.0),  # not in SYMBOL_MAP
        quote("XGLE", bid=50.0,  ask=51.0),
        quote("EWG2", bid=120.0, ask=122.0),
    ])
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))

    prices, _, _ = gather_prices(CONTRACTS, SYMBOL_MAP, STRATEGY)
    assert set(prices.keys()) == {"Equity", "Bonds", "Gold"}


# ── Unusable quote (no usable price) triggers manual fallback ───────────

def test_quote_with_no_usable_price_falls_back_to_manual(monkeypatch):
    """A quote that resolves to None or ≤0 must prompt, not silently drop."""
    monkeypatch.setattr(main, "fetch_quotes", lambda contracts: [
        quote("SPYY", bid=0, ask=0, last=0, close=0),  # all non-positive
        quote("XGLE", bid=50.0, ask=51.0),
        quote("EWG2", bid=120.0, ask=122.0),
    ])
    inputs = iter([105.50])
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: next(inputs))

    prices, _, _ = gather_prices(CONTRACTS, SYMBOL_MAP, STRATEGY)
    assert prices["Equity"] == 105.50  # from manual entry, not the zero quote