"""Tests for build_contracts — translating symbols into ib_insync Stocks.

build_contracts produces one Stock per symbol with exchange='SMART',
currency='EUR', and a per-symbol primary exchange. Symbols in the
overrides map use their listed exchange; others fall back to
DEFAULT_EXCHANGE ('IBIS'). With no overrides argument, the hardcoded
PRIMARY_EXCHANGE defaults apply (used when .pinvest is absent).
"""
import pytest

from main import (build_contracts, DEFAULT_EXCHANGE, PRIMARY_EXCHANGE)


def _contract_for(symbols, overrides=None):
    """Build contracts and index them by symbol for easy lookup."""
    contracts = {c.symbol: c for c in build_contracts(symbols, overrides)}
    return contracts


def test_build_contracts_returns_one_stock_per_symbol():
    contracts = build_contracts(["SPYY", "XGLE", "EWG2"])
    assert len(contracts) == 3
    assert {c.symbol for c in contracts} == {"SPYY", "XGLE", "EWG2"}


def test_build_contracts_sets_exchange_smart_and_currency_eur():
    contracts = _contract_for(["SPYY"])
    c = contracts["SPYY"]
    assert c.exchange == "SMART"
    assert c.currency == "EUR"


def test_build_contracts_uses_default_exchange_when_no_override():
    contracts = _contract_for(["SPYY", "XGLE"], overrides={})
    assert contracts["SPYY"].primaryExchange == DEFAULT_EXCHANGE
    assert contracts["XGLE"].primaryExchange == DEFAULT_EXCHANGE


def test_build_contracts_applies_explicit_overrides():
    contracts = _contract_for(["SPYY", "EWG2"],
                              overrides={"EWG2": "SWB"})
    assert contracts["SPYY"].primaryExchange == DEFAULT_EXCHANGE  # unaffected
    assert contracts["EWG2"].primaryExchange == "SWB"


def test_build_contracts_defaults_to_hardcoded_primary_exchange_map():
    """With no overrides arg, the PRIMARY_EXCHANGE constant is used.

    This is the path main() takes when .pinvest is absent: EWG2 → SWB,
    everything else → IBIS.
    """
    contracts = _contract_for(["SPYY", "XGLE", "EWG2"])
    assert contracts["SPYY"].primaryExchange == DEFAULT_EXCHANGE
    assert contracts["XGLE"].primaryExchange == DEFAULT_EXCHANGE
    assert contracts["EWG2"].primaryExchange == "SWB"  # from PRIMARY_EXCHANGE


def test_build_contracts_custom_overrides_replace_defaults_entirely():
    """Passing overrides={} disables the hardcoded map, even for EWG2.

    This matters for the .pinvest path: if the user's config has no
    table-form overrides, main() passes an empty map (not the hardcoded
    one), so a user who drops EWG2 for a default-exchange ticker isn't
    accidentally held to the SWB override.
    """
    contracts = _contract_for(["EWG2"], overrides={})
    assert contracts["EWG2"].primaryExchange == DEFAULT_EXCHANGE  # not SWB


def test_build_contracts_handles_empty_symbol_list():
    assert build_contracts([]) == []


def test_build_contracts_overrides_for_unlisted_symbols_are_ignored():
    """An override for a symbol not in the build list has no effect."""
    contracts = _contract_for(["SPYY"], overrides={"EWG2": "SWB"})
    assert contracts["SPYY"].primaryExchange == DEFAULT_EXCHANGE