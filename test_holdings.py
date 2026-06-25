"""Tests for gather_holdings — preloaded validation and prompt behaviour.

gather_holdings reads shares per asset from the preloaded dict (sourced
from .pinvest) or prompts interactively for the missing ones. It also
reads a EUR cash side fund (separate from share counts). Properties
pinned here:

- Non-numeric preloaded values raise a clear ValueError at the top of the
  function, before any printing — so a malformed .pinvest doesn't blow up
  mid-output with a confusing format-string error.
- Assets present in preloaded are skipped (no prompt); missing ones are
  prompted via get_float_input. TOML-integer preloaded values are
  coerced to float in the returned dict.
- Cash: when supplied (not None) it's used as-is; when None the user is
  prompted. Returns (shares, cash).
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
                        preloaded={"Equity": "ABC", "Bonds": 50, "Gold": 25},
                        cash=0.0)


def test_rejects_none_preloaded_value():
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": None, "Bonds": 50, "Gold": 25},
                        cash=0.0)


def test_rejects_list_preloaded_value():
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": [1, 2, 3]}, cash=0.0)


def test_error_message_names_the_offending_asset_and_value():
    """The message should tell the user which asset and what value failed."""
    with pytest.raises(ValueError) as excinfo:
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Bonds": "abc"}, cash=0.0)
    msg = str(excinfo.value)
    assert "Bonds" in msg
    assert "'abc'" in msg


def test_rejects_bool_preloaded_value():
    """Booleans are technically ints in Python; treat them as invalid holdings."""
    # True == 1 in Python, but a holding of `True` shares is almost certainly
    # a config error, not a real position. The guard excludes bool explicitly.
    with pytest.raises(ValueError, match="not a number"):
        gather_holdings(STRATEGY, VEHICLES,
                        preloaded={"Equity": True, "Bonds": 50, "Gold": 25},
                        cash=0.0)


def test_accepts_int_preloaded_values():
    """Integers from TOML should pass validation and be coerced to float."""
    monkeypatched_input = pytest.MonkeyPatch()
    monkeypatched_input.setattr(main, "get_float_input",
                                lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))
    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100, "Bonds": 50, "Gold": 25},
                                   cash=0.0)
    assert shares == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}
    assert all(isinstance(v, float) for v in shares.values())
    assert cash == 0.0


def test_accepts_float_preloaded_values():
    """Floats pass validation as-is."""
    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100.5, "Bonds": 50.0, "Gold": 25.0},
                                   cash=123.45)
    assert shares == {"Equity": 100.5, "Bonds": 50.0, "Gold": 25.0}
    assert cash == 123.45


# ── Prompt behaviour: preloaded assets skipped, missing prompted ───────

def test_preloaded_assets_skip_prompt(monkeypatch):
    """Assets present in preloaded must not trigger a get_float_input call.
    Cash is supplied so it doesn't prompt either."""
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))
    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0},
                                   cash=0.0)
    assert shares == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}
    assert cash == 0.0


def test_missing_assets_prompt_via_get_float_input(monkeypatch):
    """Assets absent from preloaded are prompted in strategy order. Cash is
    supplied so it doesn't add a prompt; only the 2 missing assets prompt."""
    prompted = []
    def fake_input(prompt):
        prompted.append(prompt)
        return 42.0
    monkeypatch.setattr(main, "get_float_input", fake_input)

    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100.0},  # Bonds + Gold missing
                                   cash=0.0)
    assert shares == {"Equity": 100.0, "Bonds": 42.0, "Gold": 42.0}
    assert cash == 0.0
    assert len(prompted) == 2  # only Bonds + Gold, not cash
    # Prompts mention the asset and its vehicle symbol.
    assert any("Bonds" in p and "XGLE" in p for p in prompted)
    assert any("Gold" in p and "EWG2" in p for p in prompted)


def test_no_preloaded_prompts_for_everything_including_cash(monkeypatch):
    """Empty/None preloaded + cash=None → prompt for every asset AND cash."""
    inputs = iter([100.0, 50.0, 25.0, 500.0])  # Equity, Bonds, Gold, Cash
    monkeypatch.setattr(main, "get_float_input", lambda prompt: next(inputs))

    shares, cash = gather_holdings(STRATEGY, VEHICLES, preloaded=None, cash=None)
    assert shares == {"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0}
    assert cash == 500.0


# ── Cash side fund ──────────────────────────────────────────────────────

def test_cash_supplied_does_not_prompt(monkeypatch):
    """A numeric cash value (including 0.0) means the user declared it in
    .pinvest — use as-is, don't prompt."""
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))
    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0},
                                   cash=1_000.0)
    assert cash == 1_000.0


def test_cash_none_prompts_for_cash(monkeypatch):
    """cash=None means .pinvest didn't declare it — prompt the user."""
    prompted = []
    def fake_input(prompt):
        prompted.append(prompt)
        # First 3 prompts are shares (all preloaded), so this only fires for cash.
        return 750.0
    monkeypatch.setattr(main, "get_float_input", fake_input)

    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0},
                                   cash=None)
    assert cash == 750.0
    assert len(prompted) == 1
    assert "cash" in prompted[0].lower()


def test_cash_zero_is_a_valid_explicit_value(monkeypatch):
    """cash=0.0 must NOT prompt — it's a real value the user declared."""
    monkeypatch.setattr(main, "get_float_input",
                        lambda prompt: pytest.fail(f"unexpected prompt: {prompt}"))
    shares, cash = gather_holdings(STRATEGY, VEHICLES,
                                   preloaded={"Equity": 100.0, "Bonds": 50.0, "Gold": 25.0},
                                   cash=0.0)
    assert cash == 0.0