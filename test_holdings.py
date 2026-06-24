"""Tests for gather_holdings — preloaded validation and prompt behaviour.

gather_holdings reads shares per asset from the preloaded dict (sourced
from .pinvest) or prompts interactively for the missing ones. Two
properties are pinned here:

- Non-numeric preloaded values raise a clear ValueError at the top of the
  function, before any printing — so a malformed .pinvest doesn't blow up
  mid-output with a confusing format-string error.
- Assets present in preloaded are skipped (no prompt); missing ones are
  prompted via get_float_input. TOML-integer preloaded values are
  coerced to float in the returned dict.
"""
import pytest

import main
from main import gather_holdings


STRATEGY = {"Equity": {}, "Bonds": {}, "Gold": {}}
VEHICLES = {"Equity": "SPYY", "Bonds": "XGLE", "Gold": "EWG2"}


# ── Preloaded validation ────────────────────────────────────────────────

def test_rejects_non_numeric_preloaded_value():
    """A string in preloaded must raise ValueError, not slip through to
    blow up in a print format string later."""
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": "ABC", "Bonds": 50, "Gold": 25})


def test_rejects_none_preloaded_value():
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": None, "Bonds": 50, "Gold": 25})


def test_rejects_list_preloaded_value():
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": [1, 2, 3]})


def test_error_message_names_the_offending_asset_and_value():
    """The message should tell the user which asset and what value failed."""
    with pytest.raises(ValueError) as excinfo:
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Bonds": "abc"})
    msg = str(excinfo.value)
    assert "Bonds" in msg
    assert "'abc'" in msg


def test_rejects_bool_preloaded_value():
    """Booleans are technically ints in Python; treat them as invalid holdings."""
    # True == 1 in Python, but a holding of `True` shares is almost certainly
    # a config error, not a real position. The guard excludes bool explicitly.
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": True, "Bonds": 50, "Gold": 25})


def test_accepts_int_preloaded_values():
    """Integers from TOML should pass validation and be coerced to float."""
    monkeypatched_input = pytest.MonkeyPatch()
    monkeypatched_input.setattr(main, "get_float_input",
                                lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))
    result = gather_holdings(STRATEGY, VEHICLES,
                             preloaded={"Equity": 100, "Bonds": 50, "Gold": 25})
    assert result == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}
    assert all(isinstance(v, float) for v in result.values())


def test_accepts_float_preloaded_values():
    """Floats pass validation as-is."""
    result = gather_holdings(STRATEGY, VEHICLES,
                             preloaded={"Equity": 100.5, "Bonds": 50.0, "Gold": 25.0})
    assert result == {"Equity": 100.5, "Bonds": 50.0, "Gold": 25.0}


# ── Prompt behaviour: preloaded assets skipped, missing prompted ───────

def test_preloaded_assets_skip_prompt(monkeypatch):
    """Assets present in preloaded must not trigger a get_float_input call."""
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))
    result = gather_holdings(STRATEGY, VEHICLES,
                             preloaded={"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0})
    assert result == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}


def test_missing_assets_prompt_via_get_float_input(monkeypatch):
    """Assets absent from preloaded are prompted in strategy order."""
    prompted = []
    def fake_input(prompt):
        prompted.append(prompt)
        return 42.0
    monkeypatch.setattr(main, "get_float_input", fake_input)

    result = gather_holdings(STRATEGY, VEHICLES,
                             preloaded={"Equity": 100.0})  # Bonds + Gold missing
    assert result == {"Equity": 100.0, "Bonds": 42.0, "Gold": 42.0}
    assert len(prompted) == 2
    # Prompts mention the asset and its vehicle symbol.
    assert any("Bonds" in p and "XGLE" in p for p in prompted)
    assert any("Gold" in p and "EWG2" in p for p in prompted)


def test_no_preloaded_prompts_for_everything(monkeypatch):
    """Empty/None preloaded → prompt for every asset in strategy."""
    inputs = iter([100.0, 50.0, 25.0])
    monkeypatch.setattr(main, "get_float_input", lambda prompt: next(inputs))

    result = gather_holdings(STRATEGY, VEHICLES, preloaded=None)
    assert result == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}