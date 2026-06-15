#!/usr/bin/env python3
import math

def get_float_input(prompt: str) -> float:
    while True:
        try:
            val = float(input(prompt))
            if val < 0:
                print("Value cannot be negative. Try again.")
                continue
            return val
        except ValueError:
            print("Invalid input. Please enter a number.")

def main():
    # Core Strategy Parameters (Targets and 20% Relative Bands)
    strategy = {
        "Equity": {"target": 0.60, "lower": 0.48, "upper": 0.72},
        "Bonds":  {"target": 0.25, "lower": 0.20, "upper": 0.30},
        "Gold":   {"target": 0.15, "lower": 0.12, "upper": 0.18}
    }

    print("--- 1. CURRENT PORTFOLIO HOLDINGS ---")
    current_shares = {
        "Equity": get_float_input("Current Equity ETF shares owned : "),
        "Bonds":  get_float_input("Current Bond ETF shares owned   : "),
        "Gold":   get_float_input("Current Gold ETC shares owned   : ")
    }

    print("\n--- 2. CURRENT MARKET PRICES (EUR) ---")
    prices = {
        "Equity": get_float_input("Equity ETF share price (€) : "),
        "Bonds":  get_float_input("Bond ETF share price (€)   : "),
        "Gold":   get_float_input("Gold ETC share price (€)   : ")
    }

    print("\n--- 3. INVESTMENT CASH ---")
    lump_sum = get_float_input("Amount of new cash to invest (€) [Enter 0 to run Rebalance Audit]: ")

    # Calculate current asset values and total portfolio value
    current_values = {asset: current_shares[asset] * prices[asset] for asset in strategy}
    total_current_value = sum(current_values.values())

    if total_current_value <= 0:
        print("Error: Total portfolio value must be greater than zero.")
        return

    # =========================================================================
    # MODE A: PURE REBALANCE AUDIT (Cash Input = 0)
    # =========================================================================
    if lump_sum == 0:
        print(f"\n================================================================================")
        print(f"RUNNING REBALANCE AUDIT (Total Portfolio Value: €{total_current_value:,.2f})")
        print(f"================================================================================")
        print(f"{'Asset Class':<12} | {'Current €':<12} | {'Current %':<10} | {'Target %':<10} | {'Allowed Band':<14} | {'Status':<10}")
        print("-" * 82)

        rebalance_triggered = False
        target_discrepancies = {}

        for asset, params in strategy.items():
            actual_val = current_values[asset]
            actual_pct = actual_val / total_current_value
            
            # Check if asset drifted outside its 20% relative band
            if actual_pct < params["lower"] or actual_pct > params["upper"]:
                status = "TRIGGERED"
                rebalance_triggered = True
            else:
                status = "OK"
            
            # Calculate what we *should* own to reset perfectly to target
            ideal_target_value = total_current_value * params["target"]
            target_discrepancies[asset] = ideal_target_value - actual_val

            print(f"{asset:<12} | €{actual_val:<10,.2f} | {actual_pct*100:<8.2f}% | {params['target']*100:<8.2f}% | {params['lower']*100:.1f}% - {params['upper']*100:.1f}% | {status}")

        print("-" * 82)

        if rebalance_triggered:
            print("\n[!] ALERT: One or more asset classes have breached the 20% relative tolerance bands.")
            print("Required trades to return portfolio to perfect target allocation:")
            print("=" * 60)
            
            for asset, eur_diff in target_discrepancies.items():
                price = prices[asset]
                if eur_diff > 0:
                    shares_to_buy = math.floor(eur_diff / price)
                    print(f"  -> BUY  {asset:<12} : ~{shares_to_buy:<4} shares (Targeting +€{eur_diff:,.2f})")
                elif eur_diff < 0:
                    shares_to_sell = math.ceil(abs(eur_diff) / price)
                    print(f"  -> SELL {asset:<12} : ~{shares_to_sell:<4} shares (Targeting -€{abs(eur_diff):,.2f})")
            print("=" * 60)
            print("Note: Execute sales first to generate the liquidity before placing buy orders.")
        else:
            print("\n[✓] Portfolio is well within tolerance bands. No manual rebalancing actions required.")

    # =========================================================================
    # MODE B: SMART LUMP-SUM INJECTION (Cash Input > 0)
    # =========================================================================
    else:
        new_total_target_value = total_current_value + lump_sum
        print(f"\nExisting Portfolio Value : €{total_current_value:,.2f}")
        print(f"Target Post-Investment   : €{new_total_target_value:,.2f}")

        # Calculate mathematical deficits (assets underweighted relative to new total)
        deficits = {}
        total_deficit = 0
        for asset, params in strategy.items():
            ideal_val = new_total_target_value * params["target"]
            deficit = ideal_val - current_values[asset]
            deficits[asset] = max(0.0, deficit)  # 0 if already overweight (don't sell)
            total_deficit += deficits[asset]

        # Allocate cash pro-rata based on deficits
        allocated_cash = {}
        if total_deficit > 0:
            for asset in strategy:
                allocated_cash[asset] = (deficits[asset] / total_deficit) * lump_sum
        else:
            for asset, params in strategy.items():
                allocated_cash[asset] = lump_sum * params["target"]

        print("\n" + "="*50)
        print(f"{'ASSET CLASS':<12} | {'CASH TO ROUTE':<15} | {'SHARES TO BUY'}")
        print("="*50)

        leftover_cash = 0
        for asset in strategy:
            cash_for_asset = allocated_cash[asset]
            price = prices[asset]
            
            shares_to_buy = math.floor(cash_for_asset / price)
            actual_cash_spent = shares_to_buy * price
            leftover_cash += (cash_for_asset - actual_cash_spent)

            print(f"{asset:<12} | €{cash_for_asset:<13,.2f} | {shares_to_buy} shares")

        print("="*50)
        print(f"Uninvested leftover cash (due to rounding): €{leftover_cash:.2f}\n")

if __name__ == "__main__":
    main()
