"""
ib.py — Interactive Brokers TWS quote fetcher.

Provides a single function `fetch_quotes` that:
  1. Connects to TWS
  2. Qualifies and requests market data for the supplied contracts
  3. Collects bid / ask / last / spread into structured dicts
  4. Cancels market-data streams and disconnects cleanly

Can also be run directly to demonstrate fetching the default contract set.
"""

from ib_insync import IB, Stock


def fetch_quotes(contracts, *,
                 host='127.0.0.1',
                 port=7496,
                 client_id=1,
                 readonly=True,
                 snapshot=False,
                 wait_seconds=1.5):
    """Connect to TWS, fetch quotes for *contracts*, then disconnect.

    Parameters
    ----------
    contracts : list[ib_insync.Contract]
        ib_insync Contract objects (e.g. Stock, Option, Future).
        These should already be populated with enough details; this
        function will call ``ib.qualifyContracts`` on them.
    host : str
        TWS / IB Gateway hostname or IP.
    port : int
        TWS port (7496 = live, 7497 = paper).
    client_id : int
        Unique client ID for the TWS session.
    readonly : bool
        Connect in read-only mode (default True).
    snapshot : bool
        Request snapshot market data instead of a streaming subscription.
    wait_seconds : float
        Seconds to wait for streaming data buffers to fill after
        requesting quotes.  Only relevant when ``snapshot=False``.

    Returns
    -------
    list[dict]
        One dict per contract, with keys:

        - **symbol** (*str*) – Contract symbol.
        - **bid** (*float | None*) – Best bid price.
        - **ask** (*float | None*) – Best ask price.
        - **last** (*float | None*) – Last trade price.
        - **spread_pct** (*float | None*) – Percentage spread
          ``(ask - bid) / ask * 100``, or ``None`` when a spread
          cannot be computed (e.g. one side is missing).

    Notes
    -----
    To use the returned data inside ``main.py``, the caller can extract
    prices as follows::

        quotes = fetch_quotes(contracts)
        prices = {
            q['symbol']: q['bid'] or q['last'] or 0  # your pricing logic
            for q in quotes
        }
    """
    ib = IB()
    results = []

    try:
        # 1 ─ Connect
        ib.connect(host, port, clientId=client_id, readonly=readonly)

        # 2 ─ Qualify contracts (resolve conId, exchange, etc.)
        ib.qualifyContracts(*contracts)

        # 3 ─ Request market data
        tickers = []
        for ct in contracts:
            ticker = ib.reqMktData(ct, genericTickList='',
                                   snapshot=snapshot,
                                   regulatorySnapshot=False)
            tickers.append((ct.symbol, ticker))

        # 4 ─ Wait for streaming data to settle
        ib.sleep(wait_seconds)

        # 5 ─ Collect results
        for symbol, ticker in tickers:
            bid = ticker.bid
            ask = ticker.ask
            last = ticker.last

            # Handle locked markets where one side initialises as -1
            if bid > 0 and ask == -1:
                ask = bid
            elif ask > 0 and bid == -1:
                bid = ask

            spread_pct = None
            if bid > 0 and ask > 0:
                spread_pct = (ask - bid) / ask * 100

            results.append({
                'symbol':     symbol,
                'bid':        bid if bid > 0 else None,
                'ask':        ask if ask > 0 else None,
                'last':       last if (last and last > 0) else None,
                'spread_pct': spread_pct,
            })

            # 6 ─ Cancel individual market-data stream
            ib.cancelMktData(ticker.contract)

    finally:
        # 7 ─ Disconnect
        if ib.isConnected():
            ib.disconnect()

    return results


# ── Demonstration / self-test ────────────────────────────────────────
if __name__ == '__main__':
    CONTRACTS = [
        Stock(symbol='SPYY', exchange='SMART', currency='EUR',
              primaryExchange='IBIS'),
        Stock(symbol='XGLE', exchange='SMART', currency='EUR',
              primaryExchange='IBIS'),
        Stock(symbol='4GLD', exchange='SMART', currency='EUR',
              primaryExchange='IBIS'),
        Stock(symbol='EWG2', exchange='SMART', currency='EUR',
              primaryExchange='SWB'),
    ]

    print("🔌 Connecting to TWS and fetching quotes …")
    quotes = fetch_quotes(CONTRACTS)

    print("\n📊 --- Live Market Quotes & Relative Spreads ---")
    for q in quotes:
        bid_s   = f"{q['bid']}"   if q['bid']   is not None else "Awaiting stream"
        ask_s   = f"{q['ask']}"   if q['ask']   is not None else "Awaiting stream"
        last_s  = f"{q['last']}"  if q['last']  is not None else "No recent trades"
        spr_s   = f"{q['spread_pct']:.4f}%" if q['spread_pct'] is not None else "N/A"

        print(f"[{q['symbol']}]")
        print(f"  Bid Price:        {bid_s}")
        print(f"  Ask Price:        {ask_s}")
        print(f"  Last Trade:       {last_s}")
        print(f"  🚫 Rel. Spread:     {spr_s}")
        print()

    print("🔌 Disconnected.")
