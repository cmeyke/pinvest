import math
import tomllib
from pathlib import Path

from ib_insync import Stock

from ib import fetch_quotes

# ── Hardcoded fallbacks (used when .pinvest is absent) ───────────────
DEFAULT_VEHICLES = {"Equity": "SPYY", "Bonds": "XGLE", "Gold": "EWG2"}
DEFAULT_STRATEGY_TARGETS = {"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}
DEFAULT_BAND = 0.20  # 20 % relative tolerance
PRIMARY_EXCHANGE: dict[str, str] = {"EWG2": "SWB"}  # symbol → exchange override
DEFAULT_EXCHANGE = "IBIS"


# ══════════════════════════════════════════════════════════════════════
#  Config loading
# ══════════════════════════════════════════════════════════════════════

def load_config() -> dict | None:
    """Load .pinvest if present; return None when absent or unreadable."""
    config_path = Path(__file__).parent / ".pinvest"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def build_contracts(symbols: list[str]) -> list[Stock]:
    """Build a Stock contract for each symbol."""
    return [Stock(symbol=s, exchange="SMART", currency="EUR",
                  primaryExchange=PRIMARY_EXCHANGE.get(s, DEFAULT_EXCHANGE))
            for s in symbols]


def build_strategy(targets: dict[str, float], band: float
                   ) -> dict[str, dict[str, float]]:
    """Derive lower / upper trigger bands from targets and a relative band.

    Example: target=0.60 + band=0.20 → lower=0.48, upper=0.72.
    """
    total = sum(targets.values())
    if abs(total - 1.0) > 0.01:
        print(f"⚠️  Strategy targets sum to {total:.1%}, expected 100%.")
    return {a: {"target": t,
                "lower": t * (1.0 - band),
                "upper": t * (1.0 + band)}
            for a, t in targets.items()}


# ══════════════════════════════════════════════════════════════════════
#  Input helpers
# ══════════════════════════════════════════════════════════════════════

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


def resolve_price(q: dict) -> float | None:
    """Best available price using the fallback chain.

    midprice → bid-only → ask-only → last → close → None (manual entry).
    """
    bid = q['bid']
    ask = q['ask']
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if bid is not None:
        return bid
    if ask is not None:
        return ask
    if q['last'] is not None:
        return q['last']
    if q['close'] is not None:
        return q['close']
    return None


def resolve_buy_price(q: dict) -> float | None:
    """Price for sizing BUY orders: you pay the ask.

    Falls back to the fair-value chain (mid → bid → ask → last → close)
    when no ask is quoted, so a usable price is always returned.
    """
    if q['ask'] is not None:
        return q['ask']
    return resolve_price(q)


def resolve_sell_price(q: dict) -> float | None:
    """Price for sizing SELL orders: you receive the bid.

    Falls back to the fair-value chain (mid → bid → ask → last → close)
    when no bid is quoted, so a usable price is always returned.
    """
    if q['bid'] is not None:
        return q['bid']
    return resolve_price(q)


def gather_holdings(strategy: dict,
                    vehicles: dict[str, str],
                    preloaded: dict[str, float] | None = None
                    ) -> dict[str, float]:
    """Prompt for shares; skip assets already supplied via config."""
    preloaded = preloaded or {}
    print("--- 1. CURRENT PORTFOLIO HOLDINGS ---")
    result: dict[str, float] = {}
    for asset in strategy:
        sym = vehicles.get(asset, "?")
        if asset in preloaded:
            result[asset] = preloaded[asset]
            print(f"  {asset:<8}: {preloaded[asset]:.0f} shares of {sym}"
                  f" (from .pinvest)")
        else:
            result[asset] = get_float_input(
                f"Current {asset} ({sym}) shares owned : ")
    return result


def gather_prices(contracts: list, symbol_map: dict, strategy: dict
                  ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Fetch live quotes from TWS, apply fallback chain, prompt for any missing.

    Returns three dicts keyed by asset class:

    - **prices** — fair-value (midprice) used for valuation and band-breach.
    - **buy_prices** — ask-based price for sizing BUY orders.
    - **sell_prices** — bid-based price for sizing SELL orders.

    For manually entered prices (no live quote) all three are identical.
    """
    print("\n--- 2. CURRENT MARKET PRICES (EUR) ---")
    print("🔌 Fetching live quotes from TWS …")

    try:
        quotes = fetch_quotes(contracts)
    except Exception as e:
        print(f"❌ TWS connection failed: {e}")
        print("   Falling back to manual price entry.\n")
        quotes = []

    prices: dict[str, float] = {}
    buy_prices: dict[str, float] = {}
    sell_prices: dict[str, float] = {}
    fetched: set[str] = set()

    for q in quotes:
        asset = symbol_map.get(q['symbol'])
        if asset is None:
            continue
        price = resolve_price(q)
        if price is not None and price > 0:
            prices[asset] = price
            buy_prices[asset] = resolve_buy_price(q) or price
            sell_prices[asset] = resolve_sell_price(q) or price
            fetched.add(asset)
            spread_note = (f"  (sell €{sell_prices[asset]:.2f} / "
                           f"buy €{buy_prices[asset]:.2f})")
            if q.get('spread_pct') is not None:
                spread_note += f"  spread {q['spread_pct']:.4f}%"
            print(f"  {asset:<8} ({q['symbol']}): €{price:.2f}{spread_note}")

    # Prompt manually for any asset missing a price
    for asset in strategy:
        if asset not in fetched:
            entered = get_float_input(f"{asset} share price (€) : ")
            prices[asset] = entered
            buy_prices[asset] = entered
            sell_prices[asset] = entered

    return prices, buy_prices, sell_prices


def print_portfolio_summary(strategy: dict, shares: dict, prices: dict
                            ) -> tuple[dict[str, float], float]:
    """Print portfolio value breakdown; return (current_values, total_value)."""
    current_values = {a: shares[a] * prices[a] for a in strategy}
    total = sum(current_values.values())

    print(f"\n💰 Current Portfolio Value: €{total:,.2f}")
    for a in strategy:
        print(f"  {a:<8}: {shares[a]:.0f} shares × €{prices[a]:.2f}"
              f" = €{current_values[a]:,.2f}")
    return current_values, total


# ══════════════════════════════════════════════════════════════════════
#  MODE A — Rebalance Audit (lump_sum == 0)
# ══════════════════════════════════════════════════════════════════════

def run_rebalance_audit(strategy: dict, current_values: dict,
                        total_value: float, buy_prices: dict,
                        sell_prices: dict) -> None:
    if total_value <= 0:
        print("Error: Cannot rebalance — portfolio has no value.")
        return

    print(f"\n{'='*80}")
    print(f"RUNNING REBALANCE AUDIT (Total Portfolio Value: €{total_value:,.2f})")
    print(f"{'='*80}")
    print(f"{'Asset Class':<12} | {'Current €':<12} | {'Current %':<10} | "
          f"{'Target %':<10} | {'Allowed Band':<14} | {'Status':<10}")
    print("-" * 82)

    rebalance_triggered = False
    target_discrepancies: dict[str, float] = {}

    for asset, params in strategy.items():
        actual_val = current_values[asset]
        actual_pct = actual_val / total_value

        if actual_pct < params["lower"] or actual_pct > params["upper"]:
            status = "TRIGGERED"
            rebalance_triggered = True
        else:
            status = "OK"

        ideal_target = total_value * params["target"]
        target_discrepancies[asset] = ideal_target - actual_val

        print(f"{asset:<12} | €{actual_val:<10,.2f} | {actual_pct*100:<8.2f}% | "
              f"{params['target']*100:<8.2f}% | "
              f"{params['lower']*100:.1f}% - {params['upper']*100:.1f}% | {status}")

    print("-" * 82)

    if not rebalance_triggered:
        print("\n[✓] Portfolio is well within tolerance bands. "
              "No manual rebalancing actions required.")
        return

    print("\n[!] ALERT: One or more asset classes have breached the "
          "20% relative tolerance bands.")
    print("Required trades to return portfolio to perfect target allocation:")
    print("=" * 60)

    # Phase 1: Compute buy orders and total cash needed
    buy_orders: list[tuple[str, int, float, float]] = []
    total_cash_needed = 0.0
    sell_targets: list[tuple[str, float, float]] = []

    for asset, eur_diff in target_discrepancies.items():
        if eur_diff > 0:
            price = buy_prices[asset]
            shares = math.floor(eur_diff / price)
            cash = shares * price
            buy_orders.append((asset, shares, cash, eur_diff))
            total_cash_needed += cash
        elif eur_diff < 0:
            sell_targets.append((asset, abs(eur_diff), sell_prices[asset]))

    # Phase 2: Sell proportionally to fund the buys
    if sell_targets and total_cash_needed > 0:
        total_excess = sum(excess for _, excess, _ in sell_targets)
        remaining = total_cash_needed

        for asset, excess, price in sell_targets:
            if remaining <= 0:
                break
            proportion = excess / total_excess
            target_cash = min(proportion * total_cash_needed, excess)
            shares = math.ceil(target_cash / price)
            actual_cash = shares * price
            remaining -= actual_cash
            print(f"  -> SELL {asset:<12} : ~{shares:<4} shares "
                  f"for €{price:.2f}  (Raising €{actual_cash:,.2f})")

    # Phase 3: Print buy orders
    for asset, shares, cash, eur_diff in buy_orders:
        print(f"  -> BUY  {asset:<12} : ~{shares:<4} shares "
              f"for €{buy_prices[asset]:.2f}  (Cost: €{cash:,.2f})")

    print("=" * 60)
    print("Note: Execute sales first to generate the liquidity "
          "before placing buy orders.")


# ══════════════════════════════════════════════════════════════════════
#  MODE B — Smart Lump-Sum Injection (lump_sum > 0)
# ══════════════════════════════════════════════════════════════════════

def run_lump_sum(strategy: dict, current_values: dict,
                 total_value: float, lump_sum: float,
                 buy_prices: dict) -> None:
    new_target = total_value + lump_sum
    print(f"\nExisting Portfolio Value : €{total_value:,.2f}")
    print(f"Target Post-Investment   : €{new_target:,.2f}")

    # Calculate deficits relative to the new, larger portfolio
    deficits: dict[str, float] = {}
    total_deficit = 0.0
    for asset, params in strategy.items():
        ideal = new_target * params["target"]
        deficit = ideal - current_values[asset]
        deficits[asset] = max(0.0, deficit)
        total_deficit += deficits[asset]

    # Allocate cash pro-rata based on deficits
    allocated: dict[str, float] = {}
    if total_deficit > 0:
        for asset in strategy:
            allocated[asset] = (deficits[asset] / total_deficit) * lump_sum
    else:
        for asset, params in strategy.items():
            allocated[asset] = lump_sum * params["target"]

    print("\n" + "=" * 50)
    print(f"{'ASSET CLASS':<12} | {'CASH TO ROUTE':<15} | {'SHARES TO BUY'}")
    print("=" * 50)

    leftover = 0.0
    for asset in strategy:
        cash_for = allocated[asset]
        price = buy_prices[asset]
        shares = math.floor(cash_for / price)
        spent = shares * price
        leftover += (cash_for - spent)
        print(f"{asset:<12} | €{cash_for:<13,.2f} | {shares} shares")

    print("=" * 50)
    print(f"Uninvested leftover cash (due to rounding): €{leftover:.2f}\n")


# ══════════════════════════════════════════════════════════════════════
#  Main Orchestrator
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    config = load_config()

    if config:
        vehicles = config.get("vehicles", {})
        symbol_map = {sym: asset for asset, sym in vehicles.items()}
        contracts = build_contracts(list(symbol_map.keys()))

        preloaded = {asset: float(shares)
                     for asset, shares in config.get("holdings", {}).items()}

        strat_cfg = config.get("strategy", {})
        targets = strat_cfg.get("targets", DEFAULT_STRATEGY_TARGETS)
        band = strat_cfg.get("band", DEFAULT_BAND)
    else:
        vehicles = DEFAULT_VEHICLES
        symbol_map = {sym: asset for asset, sym in vehicles.items()}
        contracts = build_contracts(list(symbol_map.keys()))
        preloaded = {}
        targets = DEFAULT_STRATEGY_TARGETS
        band = DEFAULT_BAND

    strategy = build_strategy(targets, band)

    shares = gather_holdings(strategy, vehicles, preloaded)
    prices, buy_prices, sell_prices = gather_prices(contracts, symbol_map, strategy)
    current_values, total_value = print_portfolio_summary(
        strategy, shares, prices)

    print("\n--- 3. INVESTMENT CASH ---")
    lump_sum = get_float_input(
        "Amount of new cash to invest (€) [Enter 0 to run Rebalance Audit]: ")

    if lump_sum == 0:
        run_rebalance_audit(strategy, current_values, total_value,
                            buy_prices, sell_prices)
    else:
        run_lump_sum(strategy, current_values, total_value, lump_sum,
                     buy_prices)


if __name__ == "__main__":
    main()
