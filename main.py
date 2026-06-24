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

def load_config(path: Path | None = None) -> dict | None:
    """Load .pinvest if present; return None when absent or unreadable.

    Returns ``None`` if the file is absent. If the file exists but cannot
    be parsed (malformed TOML, IO error), prints a warning describing the
    error and returns ``None`` so the caller falls back to defaults — but
    the user is now explicitly told their config was ignored, rather than
    silently getting the default 60/25/15 strategy.
    """
    config_path = path or Path(__file__).parent / ".pinvest"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        print(f"⚠️  .pinvest is unreadable ({e}); using defaults.")
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

    Raises ``ValueError`` if the targets do not sum to 1.0 (within a 1%
    tolerance). Downstream rebalance and lump-sum math divides by the
    total portfolio value and uses each target as a weight, so a
    non-100% sum would silently under- or over-allocate — for a finance
    tool this is a foot-gun worth refusing rather than warning about.
    """
    total = sum(targets.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(
            f"Strategy targets sum to {total:.1%}, expected 100%."
        )
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

def compute_rebalance(strategy: dict, current_values: dict,
                      total_value: float, buy_prices: dict,
                      sell_prices: dict) -> dict | None:
    """Compute the rebalance audit and the trades needed to restore targets.

    Returns a dict with the following keys, or ``None`` when the portfolio
    has no value to rebalance:

    - **assets** (*list[dict]*) — one per asset, in strategy order, with:
      ``asset``, ``current_eur``, ``current_pct``, ``target_pct``,
      ``lower_pct``, ``upper_pct``, ``status`` ("OK" or "TRIGGERED"),
      ``target_eur`` (ideal value at target weight), ``discrepancy``
      (``target_eur - current_eur``; positive = underweight, needs BUY).
    - **triggered** (*bool*) — True if any asset breached its band.
    - **buy_orders** (*list[dict]*) — each with ``asset``, ``shares``,
      ``cash`` (shares × buy price), ``discrepancy`` (the EUR shortfall).
    - **sell_orders** (*list[dict]*) — each with ``asset``, ``shares``,
      ``cash`` (shares × sell price), ``excess`` (the EUR surplus).
      Sells are sized proportionally to fund the buys, capped at each
      asset's excess.
    - **total_cash_needed** (*float*) — sum of buy order costs.
    - **total_cash_raised** (*float*) — sum of sell order proceeds.
    """
    if total_value <= 0:
        return None

    assets: list[dict] = []
    triggered = False
    discrepancies: dict[str, float] = {}

    for asset, params in strategy.items():
        actual_val = current_values[asset]
        actual_pct = actual_val / total_value
        status = ("TRIGGERED"
                  if actual_pct < params["lower"] or actual_pct > params["upper"]
                  else "OK")
        if status == "TRIGGERED":
            triggered = True
        ideal_target = total_value * params["target"]
        discrepancies[asset] = ideal_target - actual_val
        assets.append({
            "asset":       asset,
            "current_eur": actual_val,
            "current_pct": actual_pct,
            "target_pct":  params["target"],
            "lower_pct":   params["lower"],
            "upper_pct":   params["upper"],
            "status":      status,
            "target_eur":  ideal_target,
            "discrepancy": discrepancies[asset],
        })

    # Phase 1: Buy orders + total cash needed; collect sell targets.
    buy_orders: list[dict] = []
    sell_targets: list[tuple[str, float, float]] = []
    total_cash_needed = 0.0

    for asset, eur_diff in discrepancies.items():
        if eur_diff > 0:
            price = buy_prices[asset]
            shares = math.floor(eur_diff / price)
            cash = shares * price
            buy_orders.append({
                "asset":      asset,
                "shares":     shares,
                "cash":       cash,
                "discrepancy": eur_diff,
            })
            total_cash_needed += cash
        elif eur_diff < 0:
            sell_targets.append((asset, abs(eur_diff), sell_prices[asset]))

    # Phase 2: Sell proportionally to fund the buys.
    # Each sell's target_cash is capped at the asset's excess so we never
    # push an asset below its target weight. ceil() then rounds shares up
    # to raise at least target_cash — but that can overshoot the cap by up
    # to one share. Trim back share-by-share until the sale fits within
    # the excess, so a sell never moves an asset from over-target to
    # under-target.
    #
    # Trimming can undershoot target_cash — sometimes by a full share,
    # which is significant when the sell asset is expensive (e.g. trim
    # from 2 × €2,500 to 1 × €2,500 drops €2,500 of cash). When that
    # happens the buys as originally sized would cost more than the sells
    # raised, producing an unexecutable order list. Phase 3 below closes
    # that gap by re-sizing the buys to fit the cash actually raised.
    sell_orders: list[dict] = []
    total_cash_raised = 0.0
    if sell_targets and total_cash_needed > 0:
        total_excess = sum(excess for _, excess, _ in sell_targets)
        remaining = total_cash_needed
        for asset, excess, price in sell_targets:
            if remaining <= 0:
                break
            proportion = excess / total_excess
            target_cash = min(proportion * total_cash_needed, excess)
            shares = math.ceil(target_cash / price)
            # Trim overshoot: never sell more shares than the excess can absorb.
            while shares > 0 and shares * price > excess:
                shares -= 1
            cash = shares * price
            remaining -= cash
            total_cash_raised += cash
            sell_orders.append({
                "asset":  asset,
                "shares": shares,
                "cash":   cash,
                "excess": excess,
            })

    # Phase 3: Re-size buys to fit the cash actually raised.
    # Sells may raise less than total_cash_needed (see Phase 2 note). Walk
    # the buy list in order, spending the remaining cash on each buy up to
    # its original floored share count, so the printed order list is
    # always executable as-is (sum(buy cash) ≤ sum(sell cash)) and we
    # don't leave cash idle the way a naive proportional scale would.
    # Bought assets may end up further below target than the ideal
    # floor(discrepancy / price), but they were under-target already —
    # no new band breach is created, and the user is never asked to
    # come up with extra cash.
    if total_cash_needed > 0 and total_cash_raised < total_cash_needed:
        budget = total_cash_raised
        for b in buy_orders:
            price = buy_prices[b["asset"]]
            max_shares = b["shares"]  # original floor(discrepancy / price)
            affordable = math.floor(budget / price)
            b["shares"] = min(max_shares, affordable)
            b["cash"] = b["shares"] * price
            budget -= b["cash"]
        total_cash_needed = sum(b["cash"] for b in buy_orders)

    return {
        "assets":            assets,
        "triggered":         triggered,
        "buy_orders":        buy_orders,
        "sell_orders":       sell_orders,
        "total_cash_needed": total_cash_needed,
        "total_cash_raised": total_cash_raised,
    }


def run_rebalance_audit(strategy: dict, current_values: dict,
                        total_value: float, buy_prices: dict,
                        sell_prices: dict) -> None:
    result = compute_rebalance(strategy, current_values, total_value,
                               buy_prices, sell_prices)
    if result is None:
        print("Error: Cannot rebalance — portfolio has no value.")
        return

    print(f"\n{'='*80}")
    print(f"RUNNING REBALANCE AUDIT (Total Portfolio Value: €{total_value:,.2f})")
    print(f"{'='*80}")
    print(f"{'Asset Class':<12} | {'Current €':<12} | {'Current %':<10} | "
          f"{'Target %':<10} | {'Allowed Band':<14} | {'Status':<10}")
    print("-" * 82)

    for a in result["assets"]:
        print(f"{a['asset']:<12} | €{a['current_eur']:<10,.2f} | "
              f"{a['current_pct']*100:<8.2f}% | "
              f"{a['target_pct']*100:<8.2f}% | "
              f"{a['lower_pct']*100:.1f}% - {a['upper_pct']*100:.1f}% | "
              f"{a['status']}")

    print("-" * 82)

    if not result["triggered"]:
        print("\n[✓] Portfolio is well within tolerance bands. "
              "No manual rebalancing actions required.")
        return

    print("\n[!] ALERT: One or more asset classes have breached the "
          "20% relative tolerance bands.")
    print("Required trades to return portfolio to perfect target allocation:")
    print("=" * 60)

    for s in result["sell_orders"]:
        asset = s["asset"]
        price = sell_prices[asset]
        print(f"  -> SELL {asset:<12} : ~{s['shares']:<4} shares "
              f"for €{price:.2f}  (Raising €{s['cash']:,.2f})")

    for b in result["buy_orders"]:
        asset = b["asset"]
        price = buy_prices[asset]
        print(f"  -> BUY  {asset:<12} : ~{b['shares']:<4} shares "
              f"for €{price:.2f}  (Cost: €{b['cash']:,.2f})")

    print("=" * 60)
    print("Note: Execute sales first to generate the liquidity "
          "before placing buy orders.")


# ══════════════════════════════════════════════════════════════════════
#  MODE B — Smart Lump-Sum Injection (lump_sum > 0)
# ══════════════════════════════════════════════════════════════════════

def compute_lump_sum(strategy: dict, current_values: dict,
                     total_value: float, lump_sum: float,
                     buy_prices: dict) -> dict:
    """Compute how to route a lump sum into underweight asset classes.

    Returns a dict with:

    - **new_target** (*float*) — ``total_value + lump_sum``.
    - **deficits** (*dict[str, float]*) — EUR shortfall per asset vs. the
      new target weight (clamped to ≥ 0).
    - **total_deficit** (*float*) — sum of deficits.
    - **allocated** (*dict[str, float]*) — EUR routed to each asset.
      When ``total_deficit > 0`` cash is split pro-rata by deficit;
      otherwise it is split by target weight.
    - **orders** (*list[dict]*) — one per asset, in strategy order, with:
      ``asset``, ``cash`` (allocated), ``shares`` (floored),
      ``spent`` (shares × buy price), ``leftover`` (cash − spent).
    - **total_leftover** (*float*) — sum of per-asset leftovers from
      integer-share rounding.
    """
    new_target = total_value + lump_sum

    deficits: dict[str, float] = {}
    total_deficit = 0.0
    for asset, params in strategy.items():
        ideal = new_target * params["target"]
        deficit = max(0.0, ideal - current_values[asset])
        deficits[asset] = deficit
        total_deficit += deficit

    allocated: dict[str, float] = {}
    if total_deficit > 0:
        for asset in strategy:
            allocated[asset] = (deficits[asset] / total_deficit) * lump_sum
    else:
        for asset, params in strategy.items():
            allocated[asset] = lump_sum * params["target"]

    orders: list[dict] = []
    total_leftover = 0.0
    for asset in strategy:
        cash_for = allocated[asset]
        price = buy_prices[asset]
        shares = math.floor(cash_for / price)
        spent = shares * price
        leftover = cash_for - spent
        total_leftover += leftover
        orders.append({
            "asset":    asset,
            "cash":     cash_for,
            "shares":   shares,
            "spent":    spent,
            "leftover": leftover,
        })

    return {
        "new_target":      new_target,
        "deficits":        deficits,
        "total_deficit":   total_deficit,
        "allocated":       allocated,
        "orders":          orders,
        "total_leftover":  total_leftover,
    }


def run_lump_sum(strategy: dict, current_values: dict,
                 total_value: float, lump_sum: float,
                 buy_prices: dict) -> None:
    result = compute_lump_sum(strategy, current_values, total_value,
                              lump_sum, buy_prices)

    print(f"\nExisting Portfolio Value : €{total_value:,.2f}")
    print(f"Target Post-Investment   : €{result['new_target']:,.2f}")

    print("\n" + "=" * 50)
    print(f"{'ASSET CLASS':<12} | {'CASH TO ROUTE':<15} | {'SHARES TO BUY'}")
    print("=" * 50)

    for o in result["orders"]:
        print(f"{o['asset']:<12} | €{o['cash']:<13,.2f} | {o['shares']} shares")

    print("=" * 50)
    print(f"Uninvested leftover cash (due to rounding): "
          f"€{result['total_leftover']:.2f}\n")


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
