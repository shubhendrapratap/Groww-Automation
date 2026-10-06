from growwapi import GrowwAPI
import pyotp, time, requests, os
import pandas as pd
from datetime import datetime, timedelta
import argparse
#shubh

# ================= CONFIG - CHANGE HERE =================
SYMBOL = "RELIANCE"
QTY = 1
INTERVAL_MIN = 5 # for backtest
FAST_EMA = 9 # will be optimized
SLOW_EMA = 21
STOP_LOSS_PCT = 1.0
TARGET_PCT = 2.0
BROKERAGE = 20
SLIPPAGE_PCT = 0.05
LIVE_TRADING = False # KEEP False for testing, True to place real orders
DAILY_MAX_LOSS = -500

# === SECRETS - PUT IN.env, DELETE OLD TOKEN YOU LEAKED ===
TOTP_TOKEN = os.getenv("GROWW_TOTP_TOKEN", "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjI1NzkzMTIzMTAsImlhdCI6MTc5MDkxMjMxMCwibmJmIjoxNzkwOTEyMzEwLCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCJkM2JlZmNhNS1kOTk5LTQwYWYtOGU3Yi1jYTM2MzNkMDhlNmVcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiMmU1Zjg5NWQtMmRiNS00MGJjLTllZTYtOGM0Y2JmOGM3YjIwXCIsXCJkZXZpY2VJZFwiOlwiODk4ZGMwOTItNWIwYi01OWY4LWFhNWUtYzk5OGFmOTcwYWJhXCIsXCJzZXNzaW9uSWRcIjpcIjljY2U1MzM3LWFjN2QtNDJkMS1iYjYwLTNkM2E4MjgyYjQxMFwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYkpkbDlKZEo5NGpVblhOeEx2Y215Y1JSTkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcImF1dGgtdG90cFwiLFwic291cmNlSXBBZGRyZXNzXCI6XCIyMDMuMTEwLjI0Ny41MywxNzIuNjkuMTI5LjIyOCwzNS4yNDEuMjMuMTIzXCIsXCJ0d29GYUV4cGlyeVRzXCI6MjU3OTMxMjMxMDEzOSxcInZlbmRvck5hbWVcIjpcImdyb3d3QXBpXCJ9IiwiaXNzIjoiYXBleC1hdXRoLXByb2QtYXBwIn0.OAAWyAxr4ebZnOs7-g8G7FGIU7NziA2k7mj6YZ10NwDaPK5MHEt1CZkv558KZSz4iwXqcssEvy0Yc9PdWI7cug")
TOTP_SECRET = os.getenv("GROWW_TOTP_SECRET", "XOSCLAKBD65O6RF5OPAHBWHJRPTYYLPQ")

def login():
    my_ip = requests.get('https://api.ipify.org').text
    print(f"IP check: {my_ip} (whitelisted 203.110.247.53)")
    code = pyotp.TOTP(TOTP_SECRET).now()
    token = GrowwAPI.get_access_token(api_key=TOTP_TOKEN, totp=code)
    groww = GrowwAPI(token)
    print("Login OK")
    return groww

def fetch_history(groww, symbol, days=30):
    all_candles = []
    end = datetime.now()
    start = end - timedelta(days=days)
    curr = start
    while curr < end:
        chunk_end = min(curr + timedelta(days=14), end)
        s_str = curr.strftime("%Y-%m-%d %H:%M:%S")
        e_str = chunk_end.strftime("%Y-%m-%d %H:%M:%S")
        try:
            resp = groww.get_historical_candle_data(
                trading_symbol=symbol,
                exchange=groww.EXCHANGE_NSE,
                segment=groww.SEGMENT_CASH,
                start_time=s_str,
                end_time=e_str,
                interval_in_minutes=INTERVAL_MIN
            )
            if resp and 'candles' in resp:
                all_candles.extend(resp['candles'])
        except Exception as e:
            print(f"History chunk failed: {e}")
        curr = chunk_end
        time.sleep(1)
    df = pd.DataFrame(all_candles, columns=['ts','open','high','low','close','volume'])
    if df.empty:
        return df
    df['datetime'] = pd.to_datetime(df['ts'], unit='s')
    df = df.sort_values('datetime')
    df['close'] = df['close'].astype(float)
    return df

def add_indicators(df, fast, slow):
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=fast).mean()
    df['ema_slow'] = df['close'].ewm(span=slow).mean()
    return df

def run_backtest(df, fast, slow):
    df = add_indicators(df, fast, slow)
    in_pos = False
    buy_price = 0
    pnl = 0
    trades = 0
    wins = 0
    for i in range(1, len(df)):
        prev, curr = df.iloc[i-1], df.iloc[i]
        buy_sig = not in_pos and prev['ema_fast'] <= prev['ema_slow'] and curr['ema_fast'] > curr['ema_slow']
        sell_sig = False
        if in_pos:
            chg = (curr['close'] - buy_price)/buy_price*100
            if chg >= TARGET_PCT or chg <= -STOP_LOSS_PCT:
                sell_sig = True
            if prev['ema_fast'] >= prev['ema_slow'] and curr['ema_fast'] < curr['ema_slow']:
                sell_sig = True
        if buy_sig:
            buy_price = curr['close'] * (1+SLIPPAGE_PCT/100) + BROKERAGE/QTY
            in_pos = True
        elif sell_sig and in_pos:
            sell_price = curr['close'] * (1-SLIPPAGE_PCT/100) - BROKERAGE/QTY
            trade_pnl = (sell_price - buy_price) * QTY
            pnl += trade_pnl
            if trade_pnl > 0: wins += 1
            trades += 1
            in_pos = False
    return pnl, trades, wins

def optimize(groww):
    print("\n=== BACKTEST MODE ===")
    df = fetch_history(groww, SYMBOL, days=30)
    print(f"Fetched {len(df)} candles")
    best = None
    for fast in [7,9,12]:
        for slow in [21,26,50]:
            if fast >= slow: continue
            pnl, trades, wins = run_backtest(df, fast, slow)
            print(f"EMA {fast}/{slow} -> PnL ₹{pnl:.2f} Trades {trades} Wins {wins}")
            if best is None or pnl > best[0]:
                best = (pnl, fast, slow, trades, wins)
    print(f"\nBEST: EMA {best[1]}/{best[2]} PnL ₹{best[0]:.2f}")
    return best[1], best[2], df

def live_trading(groww, fast, slow):
    print(f"\n=== LIVE MODE EMA {fast}/{slow} Paper={not LIVE_TRADING} ===")
    daily_pnl = 0
    in_pos = False
    buy_price = 0
    df_live = pd.DataFrame(columns=['close'])

    while True:
        now = datetime.now()
        if now.hour < 9 or (now.hour == 9 and now.minute < 15) or now.hour >= 15:
            print("Market closed, sleeping 60s")
            time.sleep(60)
            continue
        try:
            # Needs paid plan, else will fail - then we use last close from history
            ltp_resp = groww.get_ltp(trading_symbol=SYMBOL, exchange=groww.EXCHANGE_NSE)
            ltp = float(ltp_resp['ltp'] if isinstance(ltp_resp, dict) else ltp_resp)
        except Exception as e:
            print(f"LTP needs paid plan: {e} - using paper simulation")
            time.sleep(60)
            continue

        # add to live df for EMA calc
        df_live.loc[len(df_live)] = [ltp]
        if len(df_live) < slow+5:
            print(f"{now.strftime('%H:%M:%S')} Warming up EMA... LTP {ltp}")
            time.sleep(60)
            continue
        df_live['ema_fast'] = df_live['close'].ewm(span=fast).mean()
        df_live['ema_slow'] = df_live['close'].ewm(span=slow).mean()
        curr = df_live.iloc[-1]
        prev = df_live.iloc[-2]

        buy_sig = not in_pos and prev['ema_fast'] <= prev['ema_slow'] and curr['ema_fast'] > curr['ema_slow']
        sell_sig = False
        if in_pos:
            chg = (ltp - buy_price)/buy_price*100
            if chg >= TARGET_PCT or chg <= -STOP_LOSS_PCT:
                sell_sig = True
            if prev['ema_fast'] >= prev['ema_slow'] and curr['ema_fast'] < curr['ema_slow']:
                sell_sig = True

        if buy_sig:
            print(f"BUY SIGNAL {SYMBOL} @ {ltp}")
            if LIVE_TRADING:
                groww.place_order(
                    trading_symbol=SYMBOL, quantity=QTY,
                    validity=groww.VALIDITY_DAY, exchange=groww.EXCHANGE_NSE,
                    segment=groww.SEGMENT_CASH, product=groww.PRODUCT_CNC,
                    order_type=groww.ORDER_TYPE_MARKET,
                    transaction_type=groww.TRANSACTION_TYPE_BUY,
                    order_reference_id=f"buy-{int(time.time())}"
                )
            in_pos = True
            buy_price = ltp

        if sell_sig and in_pos:
            print(f"SELL SIGNAL @ {ltp} P&L {(ltp-buy_price)/buy_price*100:.2f}%")
            if LIVE_TRADING:
                groww.place_order(
                    trading_symbol=SYMBOL, quantity=QTY,
                    validity=groww.VALIDITY_DAY, exchange=groww.EXCHANGE_NSE,
                    segment=groww.SEGMENT_CASH, product=groww.PRODUCT_CNC,
                    order_type=groww.ORDER_TYPE_MARKET,
                    transaction_type=groww.TRANSACTION_TYPE_SELL,
                    order_reference_id=f"sell-{int(time.time())}"
                )
            daily_pnl += (ltp - buy_price) * QTY
            in_pos = False
            if daily_pnl <= DAILY_MAX_LOSS:
                print(f"Daily max loss {DAILY_MAX_LOSS} hit, stopping")
                break
        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['backtest','live','both'], default='both')
    args = parser.parse_args()

    groww = login()
    if args.mode in ['backtest','both']:
        fast, slow, _ = optimize(groww)
        FAST_EMA, SLOW_EMA = fast, slow
    if args.mode in ['live','both']:
        live_trading(groww, FAST_EMA, SLOW_EMA)