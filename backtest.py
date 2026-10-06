from growwapi import GrowwAPI
import pyotp, time, requests, os
import pandas as pd
from datetime import datetime, timedelta

TOTP_TOKEN = "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjI1NzkzMTIzMTAsImlhdCI6MTc5MDkxMjMxMCwibmJmIjoxNzkwOTEyMzEwLCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCJkM2JlZmNhNS1kOTk5LTQwYWYtOGU3Yi1jYTM2MzNkMDhlNmVcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiMmU1Zjg5NWQtMmRiNS00MGJjLTllZTYtOGM0Y2JmOGM3YjIwXCIsXCJkZXZpY2VJZFwiOlwiODk4ZGMwOTItNWIwYi01OWY4LWFhNWUtYzk5OGFmOTcwYWJhXCIsXCJzZXNzaW9uSWRcIjpcIjljY2U1MzM3LWFjN2QtNDJkMS1iYjYwLTNkM2E4MjgyYjQxMFwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYkpkbDlKZEo5NGpVblhOeEx2Y215Y1JSTkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcImF1dGgtdG90cFwiLFwic291cmNlSXBBZGRyZXNzXCI6XCIyMDMuMTEwLjI0Ny41MywxNzIuNjkuMTI5LjIyOCwzNS4yNDEuMjMuMTIzXCIsXCJ0d29GYUV4cGlyeVRzXCI6MjU3OTMxMjMxMDEzOSxcInZlbmRvck5hbWVcIjpcImdyb3d3QXBpXCJ9IiwiaXNzIjoiYXBleC1hdXRoLXByb2QtYXBwIn0.OAAWyAxr4ebZnOs7-g8G7FGIU7NziA2k7mj6YZ10NwDaPK5MHEt1CZkv558KZSz4iwXqcssEvy0Yc9PdWI7cug"

TOTP_SECRET = "XOSCLAKBD65O6RF5OPAHBWHJRPTYYLPQ"

def get_totp_code(s):
    clean = s.strip().upper().replace('0','O').replace(' ','')
    return pyotp.TOTP(clean).now()

def login():
    code = get_totp_code(TOTP_SECRET)
    tok = GrowwAPI.get_access_token(api_key=TOTP_TOKEN, totp=code)
    return GrowwAPI(tok)

groww = login()

def fetch_history_groww(symbol, days=30):
    # NEW API: groww_symbol = "NSE-RELIANCE", candle_interval = CANDLE_INTERVAL_MIN_5
    try:
        groww_sym = f"NSE-{symbol}"
        end = datetime.now()
        start = end - timedelta(days=days)
        # Groww needs format "2025-09-24 10:56:00"
        resp = groww.get_historical_candles(
            exchange=groww.EXCHANGE_NSE,
            segment=groww.SEGMENT_CASH,
            groww_symbol=groww_sym,
            start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
            candle_interval=groww.CANDLE_INTERVAL_MIN_5 # or MIN_1, MIN_10, HOUR_1, DAY_1
        )
        print("Groww candles:", resp)
        if resp and 'candles' in resp:
            return pd.DataFrame(resp['candles'], columns=['ts','open','high','low','close','volume'])
    except Exception as e:
        print(f"Groww history forbidden (need paid ₹499 plan): {e}")
    return None

def fetch_history_free(symbol, days=30):
    # Fallback free data for backtesting - works on trial
    import yfinance as yf
    # yfinance uses RELIANCE.NS for NSE
    ticker = f"{symbol}.NS"
    df = yf.download(ticker, period=f"{days}d", interval="5m")
    df = df.reset_index()
    df.rename(columns={'Datetime':'datetime','Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'}, inplace=True)
    df['ts'] = df['datetime'].astype('int64')//10**9
    return df

# === USE ===
df = fetch_history_groww("RELIANCE", 30)
if df is None or df.empty:
    print("Switching to free yfinance data for backtest...")
    df = fetch_history_free("RELIANCE", 30)

print(f"Got {len(df)} candles")
print(df.head())