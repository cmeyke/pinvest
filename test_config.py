"""Tests for config loading and strategy-target validation.

Covers the two finance-tool safety fixes:
- load_config distinguishes 'absent' from 'malformed' and surfaces a
  warning when a present .pinvest is unreadable, so a silently-ignored
  strategy can't drift the portfolio toward the default 60/25/15.
- build_strategy rejects target sums that don't add up to 100% (within a
  1% tolerance), since downstream rebalance/lump-sum math uses the
  targets as weights and a non-unit sum would silently under/over-
  allocate.
"""
import pytest

import main
from main import build_strategy, load_config


# ── load_config: error paths ────────────────────────────────────────────

def test_load_config_returns_none_when_file_absent(tmp_path):
    assert load_config(tmp_path / ".pinvest") is None


def test_load_config_returns_dict_for_valid_file(tmp_path):
    cfg = tmp_path / ".pinvest"
    cfg.write_text(
        '[strategy]\nband = 0.20\n'
        '[strategy.targets]\nEquity = 0.60\nBonds = 0.25\nGold = 0.15\n'
    )
    config = load_config(cfg)
    assert config is not None
    assert config["strategy"]["band"] == 0.20


def test_load_config_returns_none_and_warns_on_malformed_toml(tmp_path, capsys):
    """A malformed .pinvest must not be silently treated as 'absent'."""
    cfg = tmp_path / ".pinvest"
    cfg.write_text("this is not = valid = toml =")
    config = load_config(cfg)
    assert config is None
    captured = capsys.readouterr()
    assert "⚠️" in captured.out
    assert "unreadable" in captured.out


def test_load_config_returns_none_and_warns_on_unparseable_content(tmp_path, capsys):
    """Random non-TOML bytes should produce the same warning path."""
    cfg = tmp_path / ".pinvest"
    cfg.write_text("definitely not toml at all [[[[")
    assert load_config(cfg) is None
    captured = capsys.readouterr()
    assert "unreadable" in captured.out


def test_load_config_absent_file_emits_no_warning(tmp_path, capsys):
    """A genuinely absent .pinvest should stay silent (it's the documented
    fallback-to-defaults path, not an error)."""
    assert load_config(tmp_path / ".pinvest") is None
    assert capsys.readouterr().out == ""


# ── build_strategy: target-sum enforcement ──────────────────────────────

def test_build_strategy_accepts_targets_summing_to_one():
    s = build_strategy({"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}, 0.20)
    assert s["Equity"]["target"] == pytest.approx(0.60)


def test_build_strategy_accepts_targets_within_one_percent_tolerance():
    """0.601 + 0.250 + 0.150 = 1.001 — within the 0.01 tolerance."""
    s = build_strategy({"Equity": 0.601, "Bonds": 0.250, "Gold": 0.150}, 0.20)
    assert s["Equity"]["target"] == pytest.approx(0.601)


@pytest.mark.parametrize("targets", [
    {"Equity": 0.50, "Bonds": 0.25, "Gold": 0.15},   # 0.90 — under
    {"Equity": 0.70, "Bonds": 0.25, "Gold": 0.15},   # 1.10 — over
    {"Equity": 0.33, "Bonds": 0.33, "Gold": 0.33},   # 0.99 — just under tol
    {"Equity": 0.34, "Bonds": 0.33, "Gold": 0.34},   # 1.01 — just over tol
])
def test_build_strategy_rejects_targets_not_summing_to_one(targets):
    with pytest.raises(ValueError, match="expected 100%"):
        build_strategy(targets, 0.20)


def test_build_strategy_rejects_empty_targets():
    with pytest.raises(ValueError, match="expected 100%"):
        build_strategy({}, 0.20)


def test_build_strategy_error_message_includes_actual_sum():
    """The message should tell the user what their targets summed to."""
    with pytest.raises(ValueError) as excinfo:
        build_strategy({"Equity": 0.50, "Bonds": 0.25, "Gold": 0.15}, 0.20)
    assert "90.0%" in str(excinfo.value)


# ── resolve_config: partial-config fallback ─────────────────────────────
#
# main() used to call config.get("vehicles", {}) which, for a present
# .pinvest with no [vehicles] section, returned {} — silently producing
# an empty symbol_map, no contracts, no fetched prices, and prompts with
# "?" as the ticker. resolve_config now falls back to DEFAULT_VEHICLES
# whenever vehicles is missing *or* empty, and similarly for targets.

from main import resolve_config, DEFAULT_VEHICLES, DEFAULT_STRATEGY_TARGETS, DEFAULT_BAND


def test_resolve_config_returns_defaults_when_config_is_none():
    r = resolve_config(None)
    assert r["vehicles"] == DEFAULT_VEHICLES
    assert r["preloaded"] == {}
    assert r["targets"] == DEFAULT_STRATEGY_TARGETS
    assert r["band"] == DEFAULT_BAND


def test_resolve_config_uses_config_values_when_complete():
    config = {
        "vehicles": {"Equity": "SPYY", "Bonds": "XGLE", "Gold": "EWG2"},
        "holdings": {"Equity": 100, "Bonds": 50, "Gold": 25},
        "strategy": {"band": 0.15, "targets": {"Equity": 0.50, "Bonds": 0.30, "Gold": 0.20}},
    }
    r = resolve_config(config)
    assert r["vehicles"] == {"Equity": "SPYY", "Bonds": "XGLE", "Gold": "EWG2"}
    assert r["preloaded"] == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}
    assert r["targets"] == {"Equity": 0.50, "Bonds": 0.30, "Gold": 0.20}
    assert r["band"] == 0.15


def test_resolve_config_falls_back_when_vehicles_section_missing():
    """A .pinvest with no [vehicles] should use DEFAULT_VEHICLES, not {}."""
    r = resolve_config({"strategy": {"band": 0.20}})
    assert r["vehicles"] == DEFAULT_VEHICLES


def test_resolve_config_falls_back_when_vehicles_section_empty():
    """An empty [vehicles] table should also fall back, not produce {}."""
    r = resolve_config({"vehicles": {}, "strategy": {"band": 0.20}})
    assert r["vehicles"] == DEFAULT_VEHICLES


def test_resolve_config_falls_back_when_targets_missing():
    """A .pinvest with no [strategy.targets] should use DEFAULT_STRATEGY_TARGETS."""
    r = resolve_config({"vehicles": {"Equity": "X"}, "strategy": {"band": 0.20}})
    assert r["targets"] == DEFAULT_STRATEGY_TARGETS


def test_resolve_config_falls_back_when_targets_empty():
    r = resolve_config({"strategy": {"band": 0.20, "targets": {}}})
    assert r["targets"] == DEFAULT_STRATEGY_TARGETS


def test_resolve_config_falls_back_when_band_missing():
    """A .pinvest with no band should use DEFAULT_BAND."""
    r = resolve_config({"strategy": {"targets": {"Equity": 0.6, "Bonds": 0.25, "Gold": 0.15}}})
    assert r["band"] == DEFAULT_BAND


def test_resolve_config_preloaded_empty_when_holdings_missing():
    """No [holdings] section → empty preloaded dict → prompts for all assets."""
    r = resolve_config({"vehicles": {"Equity": "SPYY"}, "strategy": {"band": 0.20}})
    assert r["preloaded"] == {}


def test_resolve_config_preloaded_converts_values_to_float():
    """TOML integers must become floats so downstream math stays float."""
    r = resolve_config({"holdings": {"Equity": 455, "Bonds": 236}})
    assert r["preloaded"] == {"Equity": 455.0, "Bonds": 236.0}
    assert all(isinstance(v, float) for v in r["preloaded"].values())