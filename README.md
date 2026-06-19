# Portfolio Rebalance & Asset Allocation Tracker

A lightweight, terminal-based Python tool engineered to manage a **60/25/15**
asset allocation strategy using a **20% relative tolerance band** dynamic.
It fetches live prices from Interactive Brokers TWS, tracks drift, and
calculates precision order execution sizes.

> **Disclaimer:** This tool is provided for informational and educational
> purposes only.  It does **not** constitute financial advice.  All
> investment decisions and associated risks are solely your own.  Verify
> every trade independently before placing it with real funds.

## Strategy Architecture

The default strategy is a **60 / 25 / 15** allocation with a **20%**
relative tolerance band.  Both the targets and the band are configurable
in `.pinvest` (see below).

| Asset Class          | Target Allocation | Lower Trigger Band | Upper Trigger Band |
| :------------------- | :---------------: | :----------------: | :----------------: |
| **Global Equities**  |      60.0%        |       48.0%        |       72.0%        |
| **Eurozone Bonds**   |      25.0%        |       20.0%        |       30.0%        |
| **Physical Gold**    |      15.0%        |       12.0%        |       18.0%        |

---

## Key Features

- **Live Pricing via TWS:** Pulls bid/ask/last/close from Interactive Brokers.
  Uses midprice as the fair-value estimate with a 6-tier fallback chain
  (midprice → bid → ask → last → close → manual entry) so you always get
  a usable price even when the exchange is closed.
- **Dual-Mode Execution:** Alternates automatically between smart cash
  placement and threshold rebalancing based on your inputs.
- **Smart Lump-Sum Injection (Cash > 0):** Automatically routes fresh
  capital directly into underweighted asset classes to fix portfolio drift,
  minimizing the need to sell assets and cross expensive bid-ask spreads.
- **Rebalance Audit (Cash = 0):** Runs a targeted check against your 20%
  relative thresholds. Alerts you and outputs exact buy/sell orders in
  whole shares only if a boundary has been crossed.
- **Integer Rounding Control:** Uses floor (buy) / ceil (sell) logic to
  guarantee you don't accidentally overdraw your broker's cash balance.

---

## Requirements

- **Python 3.13+**
- [Interactive Brokers TWS](https://www.interactivebrokers.com/) or IB
  Gateway running locally (API port 7496)
- [`uv`](https://docs.astral.sh/uv/) for dependency management

```bash
uv sync
```

The only external dependency is `ib-insync`.

---

## Configuration (`.pinvest`)

Copy `.pinvest.example` to `.pinvest` and edit to match your portfolio:

```toml
[strategy]
band = 0.20               # 20 % relative tolerance

[strategy.targets]
Equity = 0.60             # must sum to 1.0
Bonds  = 0.25
Gold   = 0.15

[holdings]
Equity = 150
Bonds  = 85
Gold   = 60

[vehicles]
Equity = "SPYY"
Bonds  = "XGLE"
Gold   = "EWG2"
```

- **`[strategy]`** — target allocations and tolerance band.  Lower and
  upper trigger bands are derived automatically (target ± band).
- **`[holdings]`** — number of shares you own per asset class.  Assets
  listed here skip the interactive prompt.
- **`[vehicles]`** — which ETF / ETC ticker to use for each asset class.
  Change a ticker here only; holdings stay untouched.

`.pinvest` is git-ignored so your personal holdings stay local.  If the
file is absent the tool falls back to hardcoded defaults (60/25/15 with
20 % band; SPYY / XGLE / EWG2) and prompts for everything interactively.

---

## Usage

```bash
uv run main.py
```

---

## Scenario A: Smart Lump-Sum Injection

When you have fresh capital to deploy (e.g., monthly savings), enter the
Euro amount at the prompt.  The tool routes cash proportionally to
underweighted assets without selling any current shares.

```text
--- 1. CURRENT PORTFOLIO HOLDINGS ---
  Equity  : 150 shares of SPYY (from .pinvest)
  Bonds   : 85 shares of XGLE (from .pinvest)
  Gold    : 60 shares of EWG2 (from .pinvest)

--- 2. CURRENT MARKET PRICES (EUR) ---
🔌 Fetching live quotes from TWS …
  Equity   (SPYY): €105.50
  Bonds    (XGLE): €52.20
  Gold     (EWG2): €121.05

💰 Current Portfolio Value: €27,525.00
  Equity  : 150 shares × €105.50 = €15,825.00
  Bonds   : 85 shares × €52.20 = €4,437.00
  Gold    : 60 shares × €121.05 = €7,263.00

--- 3. INVESTMENT CASH ---
Amount of new cash to invest (€) [Enter 0 to run Rebalance Audit]: 3000

Existing Portfolio Value : €27,525.00
Target Post-Investment   : €30,525.00

==================================================
ASSET CLASS  | CASH TO ROUTE   | SHARES TO BUY
==================================================
Equity       | €1,314.16       | 12 shares
Bonds        | €1,685.84       | 32 shares
Gold         | €0.00           | 0 shares
==================================================
Uninvested leftover cash (due to rounding): €63.60
```

> Gold receives €0 because it is already above its target weight when
> the new cash is included — the tool never sells in lump-sum mode.

---

## Scenario B: Threshold Rebalance Audit

During your quarterly review enter **0** as the cash amount.  The script
evaluates current weights and only triggers actionable trades when a 20%
relative band has been breached.

```text
💰 Current Portfolio Value: €27,525.00
  Equity  : 150 shares × €105.50 = €15,825.00
  Bonds   : 85 shares × €52.20 = €4,437.00
  Gold    : 60 shares × €121.05 = €7,263.00

--- 3. INVESTMENT CASH ---
Amount of new cash to invest (€) [Enter 0 to run Rebalance Audit]: 0

================================================================================
RUNNING REBALANCE AUDIT (Total Portfolio Value: €27,525.00)
================================================================================
Asset Class  | Current €    | Current %  | Target %   | Allowed Band   | Status
--------------------------------------------------------------------------------
Equity       | €15,825.00   | 57.49%     | 60.00%     | 48.0% - 72.0%  | OK
Bonds        | €4,437.00    | 16.12%     | 25.00%     | 20.0% - 30.0%  | TRIGGERED
Gold         | €7,263.00    | 26.39%     | 15.00%     | 12.0% - 18.0%  | TRIGGERED
--------------------------------------------------------------------------------

[!] ALERT: One or more asset classes have breached the 20% relative
    tolerance bands.
Required trades to return portfolio to perfect target allocation:
============================================================
  -> SELL Gold         : ~26   shares (Raising €3,147.30)
  -> BUY  Equity       : ~6    shares (Cost: €633.00)
  -> BUY  Bonds        : ~46   shares (Cost: €2,401.20)
============================================================
Note: Execute sales first to generate the liquidity before placing
      buy orders.
```
