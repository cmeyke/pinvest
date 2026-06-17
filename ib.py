from ib_insync import *

ib = IB()

try:
    # 1. Connect cleanly to the Live Port (7496) in Read-Only Mode
    print("🔌 Connecting to live TWS engine...")
    ib.connect('127.0.0.1', 7496, clientId=1, readonly=True)
    
    # 2. Define your optimized European asset structural matrix
    contracts = [
        Stock(symbol='SPYY', exchange='SMART', currency='EUR', primaryExchange='IBIS'),
        Stock(symbol='XGLE', exchange='SMART', currency='EUR', primaryExchange='IBIS'),
        Stock(symbol='4GLD', exchange='SMART', currency='EUR', primaryExchange='IBIS'),
        Stock(symbol='EWG2', exchange='SMART', currency='EUR', primaryExchange='SWB')
    ]
    
    ib.qualifyContracts(*contracts)
    
    # 3. Spin up continuous streaming data pipelines (snapshot=False)
    tickers = []
    for contract in contracts:
        ticker = ib.reqMktData(contract, genericTickList='', snapshot=False, regulatorySnapshot=False)
        tickers.append((contract.symbol, ticker))
    
    print("⚡ Synchronizing live order books and calculating friction spreads...")
    ib.sleep(1.5)  # 1.5s window allows streaming buffers to catch initial data packets
    
    print("\n📊 --- Live Market Quotes & Relative Spreads ---")
    for symbol, ticker in tickers:
        bid = ticker.bid
        ask = ticker.ask
        last = ticker.last
        
        # 4. Handle the locked-market conditions where one side initializes as -1
        if bid > 0 and ask == -1:
            ask = bid  # Mirror bid if ask is compressed/locked at -1
        elif ask > 0 and bid == -1:
            bid = ask  # Mirror ask if bid is compressed/locked at -1

        # 5. Compute percentage spreads and format data strings
        if bid > 0 and ask > 0:
            absolute_spread = ask - bid
            percentage_spread = (absolute_spread / ask) * 100
            
            bid_str = f"{bid}"
            ask_str = f"{ask}"
            spread_str = f"{percentage_spread:.4f}%" if percentage_spread > 0 else "0.0000% (Zero/Locked Spread)"
        else:
            # Fallback block if the network channel is completely empty
            bid_str = f"{bid}" if bid > 0 else "Awaiting stream"
            ask_str = f"{ask}" if ask > 0 else "Awaiting stream"
            spread_str = "N/A"
            
        last_str = f"{last}" if (last and last > 0) else "No recent trades"

        print(f"[{symbol}]")
        print(f"  Bid Price:     {bid_str}")
        print(f"  Ask Price:     {ask_str}")
        print(f"  Last Trade:    {last_str}")
        print(f"  🚫 Relative Spread: {spread_str}")
        print()
        
    # 6. Tear down active pipelines to clean out TWS background network frames
    for _, ticker in tickers:
        ib.cancelMktData(ticker.contract)

except Exception as e:
    print(f"❌ Execution Failure: {e}")

finally:
    if ib.isConnected():
        ib.disconnect()
        print("🔌 Local system pipeline disconnected safely.")
