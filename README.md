# Portfolio Rebalance & Asset Allocation Tracker

A lightweight, terminal-based Python tool engineered to manage a **60/25/15** asset allocation strategy using a **20% relative tolerance band** dynamic. It helps maximize efficiency by tracking drift and calculating precision order execution sizes.

## Strategy Architecture

The script monitors three core asset classes within an institutional-grade opportunistic framework:

| Asset Class | Target Allocation | Lower Trigger Band | Upper Trigger Band |
| :--- | :---: | :---: | :---: |
| **Global Equities** | 60.0% | 48.0% | 72.0% |
| **Eurozone Bonds** | 25.0% | 20.0% | 30.0% |
| **Physical Gold (ETC)**| 15.0% | 12.0% | 18.0% |

---

## Key Features

- **Dual-Mode Execution:** Alternates automatically between smart cash placement and threshold rebalancing based on your inputs.
- **Smart Lump-Sum Injection (Cash > 0):** Automatically routes fresh capital directly into underweighted asset classes to fix portfolio drift, minimizing the need to sell assets and cross expensive bid-ask spreads.
- **Rebalance Audit (Cash = 0):** Runs a targeted check against your 20% relative thresholds. It alerts you and outputs the exact buy/sell orders in whole shares only if a boundary has been crossed.
- **Integer Rounding Control:** Uses floor/ceiling logic to guarantee you don't accidentally overdraw your broker's cash balance when purchasing whole shares.

---

## Requirements

The script is written in native Python 3 and has **zero external dependencies**.

---

## Scenario A: Smart Lump-Sum Injection

When you have fresh capital to deploy (e.g., monthly/quarterly savings), enter the Euro amount at the prompt. The tool will calculate how to bring you closest to your target allocation without selling any current shares.

```text
--- 1. CURRENT PORTFOLIO HOLDINGS ---
Current Equity ETF shares owned : 150
Current Bond ETF shares owned   : 85
Current Gold ETC shares owned   : 60

--- 2. CURRENT MARKET PRICES (EUR) ---
Equity ETF share price (€) : 105.50
Bond ETF share price (€)   : 52.20
Gold ETC share price (€)   : 121.05

--- 3. INVESTMENT CASH ---
Amount of new cash to invest (€) [Enter 0 to run Rebalance Audit]: 3000

==================================================
ASSET CLASS  | CASH TO ROUTE   | SHARES TO BUY
==================================================
Equity       | €1,800.00       | 17 shares
Bonds        | €750.00         | 14 shares
Gold         | €450.00         | 3 shares
==================================================
Uninvested leftover cash (due to rounding): €43.55
```

---

## Scenario B: Threshold Rebalance Audit

During your quarterly calendar review, enter 0 as the investment cash amount. The script evaluates your current asset weights and triggers an actionable trade breakdown only if a 20% relative tolerance band has been violated.

```text
--- 3. INVESTMENT CASH ---
Amount of new cash to invest (€) [Enter 0 to run Rebalance Audit]: 0

================================================================================
RUNNING REBALANCE AUDIT (Total Portfolio Value: €27,510.50)
================================================================================
Asset Class  | Current €    | Current %  | Target %   | Allowed Band   | Status    
--------------------------------------------------------------------------------
Equity       | €15,825.00   | 57.52%     | 60.00%     | 48.0% - 72.0%  | OK        
Bonds        | €4,437.00    | 16.13%     | 25.00%     | 20.0% - 30.0%  | TRIGGERED 
Gold         | €7,248.50    | 26.35%     | 15.00%     | 12.0% - 18.0%  | TRIGGERED 
--------------------------------------------------------------------------------

[!] ALERT: One or more asset classes have breached the 20% relative tolerance bands.
Required trades to return portfolio to perfect target allocation:
============================================================
  -> BUY  Bonds        : ~46   shares (Targeting +€2,440.63)
  -> SELL Gold         : ~26   shares (Targeting -€3,121.93)
============================================================
Note: Execute sales first to generate the liquidity before placing buy orders.
```
---
