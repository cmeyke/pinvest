"""End-to-end audit: config → build_strategy → strategy matches expectations."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main
from pathlib import Path

CFG = Path(__file__).parent / ".pinvest"
backup = CFG.read_bytes() if CFG.exists() else None

try:
    CFG.write_text("""\
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

    config = main.load_config()
    assert config is not None

    strat_cfg = config.get("strategy", {})
    targets = strat_cfg.get("targets", main.DEFAULT_STRATEGY_TARGETS)
    band = strat_cfg.get("band", main.DEFAULT_BAND)
    strategy = main.build_strategy(targets, band)

    # 1. Targets match config
    assert strategy["Equity"]["target"] == 0.60
    assert strategy["Bonds"]["target"]  == 0.25
    assert strategy["Gold"]["target"]   == 0.15

    # 2. Bands derived correctly (target * (1 ± band))
    assert strategy["Equity"]["lower"] == 0.48   # 0.60 * 0.80
    assert strategy["Equity"]["upper"] == 0.72   # 0.60 * 1.20
    assert strategy["Bonds"]["lower"]  == 0.20
    assert strategy["Bonds"]["upper"]  == 0.30
    assert strategy["Gold"]["lower"]   == 0.12
    assert strategy["Gold"]["upper"]   == 0.18

    # 3. Non-default targets + band produce correct output
    strategy2 = main.build_strategy(
        {"Equity": 0.50, "Bonds": 0.30, "Gold": 0.20},
        0.15,
    )
    assert strategy2["Equity"]["lower"] == 0.425   # 0.50 * 0.85
    assert strategy2["Equity"]["upper"] == 0.575   # 0.50 * 1.15
    assert strategy2["Bonds"]["lower"]  == 0.255   # 0.30 * 0.85
    assert strategy2["Gold"]["lower"]   == 0.170   # 0.20 * 0.85

    print("All strategy tests passed ✓")
finally:
    if backup is not None:
        CFG.write_bytes(backup)
    elif CFG.exists():
        CFG.unlink()
