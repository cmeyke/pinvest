"""Tests for config loading and strategy band derivation."""
import textwrap
from pathlib import Path

import pytest

import main


# ── Fixtures ────────────────────────────────────────────────────────────

PINVEST_TOML = textwrap.dedent("""\
    [strategy]
    band = 0.20

    [strategy.targets]
    Equity = 0.60
    Bonds = 0.25
    Gold = 0.15

    [holdings]
    Equity = 455
    Bonds = 236
    Gold = 263

    [vehicles]
    Equity = "SPYY"
    Bonds = "XGLE"
    Gold = "EWG2"
""")


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """A temporary .pinvest file inside an isolated tmp_path."""
    cfg = tmp_path / ".pinvest"
    cfg.write_text(PINVEST_TOML)
    return cfg


# ── load_config ──────────────────────────────────────────────────────────

def test_load_config_returns_dict_when_present(config_file: Path):
    config = main.load_config(config_file)
    assert config is not None
    assert config["strategy"]["band"] == 0.20
    assert config["holdings"]["Equity"] == 455
    assert config["vehicles"]["Gold"] == "EWG2"


def test_load_config_returns_none_when_absent(tmp_path: Path):
    missing = tmp_path / ".pinvest"
    assert main.load_config(missing) is None


# ── build_strategy: targets & band derivation ───────────────────────────

@pytest.mark.parametrize(
    "asset,target,lower,upper",
    [
        ("Equity", 0.60, 0.48, 0.72),
        ("Bonds",  0.25, 0.20, 0.30),
        ("Gold",   0.15, 0.12, 0.18),
    ],
)
def test_build_strategy_default_band(asset, target, lower, upper):
    s = main.build_strategy(
        {"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}, 0.20
    )
    assert s[asset]["target"] == pytest.approx(target)
    assert s[asset]["lower"]  == pytest.approx(lower)
    assert s[asset]["upper"]  == pytest.approx(upper)


@pytest.mark.parametrize(
    "asset,lower,upper",
    [
        ("Equity", 0.425, 0.575),
        ("Bonds",  0.255, 0.345),
        ("Gold",   0.170, 0.230),
    ],
)
def test_build_strategy_custom_band(asset, lower, upper):
    s = main.build_strategy(
        {"Equity": 0.50, "Bonds": 0.30, "Gold": 0.20}, 0.15
    )
    assert s[asset]["lower"] == pytest.approx(lower)
    assert s[asset]["upper"] == pytest.approx(upper)