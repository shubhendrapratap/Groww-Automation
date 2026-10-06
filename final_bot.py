from growwapi import GrowwAPI
import pyotp, time, requests, os, argparse
import pandas as pd
from datetime import datetime, timedelta


# ================= CONFIG =================
SYMBOL = "RELIANCE"
QTY = 1
INTERVAL_MIN = 5
STOP_LOSS_PCT = 1.0
TARGET_PCT = 2.0
BROKERAGE = 20
SLIPPAGE_PCT = 0.05
LIVE_TRADING = False # KEEP False = paper only. True = real orders
DAILY_MAX_LOSS = -500
TOTP_TOKEN = "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjI1Nzk2NTcxNzMsImlhdCI6MTc5MTI1NzE3MywibmJmIjoxNzkxMjU3MTczLCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCIxODI0YWYyNC1jMDJjLTQ0OTItODBlYS03YTU5MTU4ODRiNGRcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiMmU1Zjg5NWQtMmRiNS00MGJjLTllZTYtOGM0Y2JmOGM3YjIwXCIsXCJkZXZpY2VJZFwiOlwiODk4ZGMwOTItNWIwYi01OWY4LWFhNWUtYzk5OGFmOTcwYWJhXCIsXCJzZXNzaW9uSWRcIjpcIjQ4NzY4MWE5LTcwZTktNDE1My04MzBkLWRjM2NiZGZjZDJmYVwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYkpkbDlKZEo5NGpVblhOeEx2Y215Y1JSTkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcImF1dGgtdG90cFwiLFwic291cmNlSXBBZGRyZXNzXCI6XCIyMDMuMTEwLjI0Ny43NCwxNzIuNjguMTQ3LjIyMywzNS4yNDEuMjMuMTIzXCIsXCJ0d29GYUV4cGlyeVRzXCI6MjU3OTY1NzE3MzkyMSxcInZlbmRvck5hbWVcIjpcImdyb3d3QXBpXCJ9IiwiaXNzIjoiYXBleC1hdXRoLXByb2QtYXBwIn0.BfL7ujm4mbOJzxIF4Be3oRzffv80TeLZ1p0vGtU0ubbbPOUaxShjRtw6w-5y5VOMb5NUEb_NvDxJlEaCM5KNug"
TOTP_SECRET = "AVWVVE5RIW4WKOYA6NAMJF5UOPRLYYST" 

# ================= HELPERS =================
def get_totp_code(raw):
    clean = raw.strip().upper().replace('0','O').replace('1','I').replace(' ','')
    return pyotp.TOTP(clean).now()

def login():
    my_ip = requests.get('https://api.ipify.org').text
    print(f"My IP: {my_ip} | Whitelisted: 203.110.247.53")
    if my_ip!= "203.110.247.53":
        print("WARNING: IP changed! Groww will block orders. Update IP or use VPS.")
    code = get_totp_code(TOTP_SECRET)
    print(f"TOTP: {code}")
    access_token = GrowwAPI.get_access_token(api_key=TOTP_TOKEN, totp=code)
    groww = GrowwAPI(access_token)
    print("Ready to Groww! Login OK\n")
    return groww

def fetch_groww_history(groww, symbol, days=30):
    try:
        groww_sym = f"NSE-{symbol}"
        end = datetime.now()
        start = end - timedelta(days=days)
        resp = groww.get_historical_candles(
            exchange=groww.EXCHANGE_NSE,
            segment=groww.SEGMENT_CASH,
            groww_symbol=groww_sym,
            start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
            candle_interval=groww.CANDLE_INTERVAL_MIN_5
        )
        if resp and 'candles' in resp and resp['candles']:
            df = pd.DataFrame(resp['candles'], columns=['ts','open','high','low','close','volume'])
            df['datetime'] = pd.to_datetime(df['ts'], unit='s')
            df['close'] = df['close'].astype(float)
            return df.sort_values('datetime')
    except Exception as e:
        print(f"Groww history forbidden (needs ₹499 plan): {e}")
    return None

def fetch_free_history(symbol, days=30):
    import yfinance as yf
    ticker = f"{symbol}.NS"
    df = yf.download(ticker, period=f"{days}d", interval="5m",
                     auto_adjust=True, multi_level_index=False, progress=False)
    if df.empty:
        return df
    df = df.reset_index()
    df.rename(columns={'Datetime':'datetime','Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'}, inplace=True)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['ts'] = df['datetime'].astype('int64')//10**9
    df = df.dropna(subset=['close']).sort_values('datetime')
    return df[['ts','datetime','open','high','low','close','volume']]

def get_history(groww, symbol, days=30):
    df = fetch_groww_history(groww, symbol, days)
    if df is None or df.empty:
        print("Switching to free yfinance for backtest...")
        df = fetch_free_history(symbol, days)
    print(f"Got {len(df)} candles from {df['datetime'].min()} to {df['datetime'].max()}\n")
    return df

def run_backtest(df, fast, slow):
    d = df.copy()
    d['ema_fast'] = d['close'].ewm(span=fast).mean()
    d['ema_slow'] = d['close'].ewm(span=slow).mean()
    in_pos = False
    buy_price = 0
    pnl = 0
    trades = 0
    wins = 0
    for i in range(1, len(d)):
        prev, curr = d.iloc[i-1], d.iloc[i]
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
            trades += 1
            if trade_pnl > 0: wins += 1
            in_pos = False
    return pnl, trades, wins

def optimize(groww, days=30):
    df = get_history(groww, SYMBOL, days)
    best = (-99999, 9, 21, 0, 0)
    for fast in [7,9,12]:
        for slow in [21,26,50]:
            if fast >= slow: continue
            pnl, trades, wins = run_backtest(df, fast, slow)
            print(f"EMA {fast}/{slow} -> PnL ₹{pnl:.2f} | Trades {trades} | Wins {wins}")
            if pnl > best[0]:
                best = (pnl, fast, slow, trades, wins)
    print(f"\n>>> BEST: EMA {best[1]}/{best[2]} PnL ₹{best[0]:.2f} Trades {best[3]} Wins {best[4]}\n")
    return best[1], best[2], df

def live_loop(groww, fast, slow):
    print(f"=== LIVE PAPER MODE EMA {fast}/{slow} LIVE_TRADING={LIVE_TRADING} ===")
    print("Market hours 9:15-15:30. Press Ctrl+C to stop.\n")
    daily_pnl = 0
    in_pos = False
    buy_price = 0
    closes = []
    while True:
        now = datetime.now()
        if now.hour < 9 or (now.hour==9 and now.minute<15) or now.hour>=15 or now.weekday()>=5:
            print(f"{now.strftime('%H:%M:%S')} Market closed, sleeping 60s")
            time.sleep(60)
            continue
        try:
            # Needs paid plan, will fail on trial - that's ok, we stay in paper
            resp = groww.get_ltp(trading_symbol=SYMBOL, exchange=groww.EXCHANGE_NSE)
            ltp = float(resp['ltp'] if isinstance(resp, dict) and 'ltp' in resp else resp)
        except Exception as e:
            print(f"LTP needs paid plan: {e} | Paper mode continues")
            time.sleep(60)
            continue

        closes.append(ltp)
        if len(closes) < slow+5:
            print(f"{now.strftime('%H:%M:%S')} Warmup {len(closes)}/{slow+5} LTP {ltp}")
            time.sleep(60)
            continue

        s = pd.Series(closes)
        ema_f = s.ewm(span=fast).mean().iloc[-1]
        ema_f_prev = s.ewm(span=fast).mean().iloc[-2]
        ema_s = s.ewm(span=slow).mean().iloc[-1]
        ema_s_prev = s.ewm(span=slow).mean().iloc[-2]

        buy_sig = not in_pos and ema_f_prev <= ema_s_prev and ema_f > ema_s
        sell_sig = False
        if in_pos:
            chg = (ltp - buy_price)/buy_price*100
            if chg >= TARGET_PCT or chg <= -STOP_LOSS_PCT:
                sell_sig = True
            if ema_f_prev >= ema_s_prev and ema_f < ema_s:
                sell_sig = True

        if buy_sig:
            print(f"BUY SIGNAL {SYMBOL} @ {ltp}")
            if LIVE_TRADING:
                groww.place_order(trading_symbol=SYMBOL, quantity=QTY, validity=groww.VALIDITY_DAY,
                                  exchange=groww.EXCHANGE_NSE, segment=groww.SEGMENT_CASH,
                                  product=groww.PRODUCT_CNC, order_type=groww.ORDER_TYPE_MARKET,
                                  transaction_type=groww.TRANSACTION_TYPE_BUY,
                                  order_reference_id=f"buy-{int(time.time())}")
            in_pos = True
            buy_price = ltp

        if sell_sig and in_pos:
            pnl = (ltp - buy_price) * QTY
            daily_pnl += pnl
            print(f"SELL @ {ltp} P&L ₹{pnl:.2f} Daily ₹{daily_pnl:.2f}")
            if LIVE_TRADING:
                groww.place_order(trading_symbol=SYMBOL, quantity=QTY, validity=groww.VALIDITY_DAY,
                                  exchange=groww.EXCHANGE_NSE, segment=groww.SEGMENT_CASH,
                                  product=groww.PRODUCT_CNC, order_type=groww.ORDER_TYPE_MARKET,
                                  transaction_type=groww.TRANSACTION_TYPE_SELL,
                                  order_reference_id=f"sell-{int(time.time())}")
            in_pos = False
            if daily_pnl <= DAILY_MAX_LOSS:
                print(f"Daily max loss {DAILY_MAX_LOSS} hit, stopping")
                break
        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['backtest','live','both'], default='both')
    parser.add_argument('--days', type=int, default=30)
    args = parser.parse_args()

    groww = login()
    fast, slow = 9, 21
    if args.mode in ['backtest','both']:
        fast, slow, _ = optimize(groww, days=args.days)
    if args.mode in ['live','both']:
        live_loop(groww, fast, slow)