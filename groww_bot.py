from growwapi import GrowwAPI
import pyotp, time, requests
from datetime import datetime

# === CONFIG - PUT IN .env LATER ===
TOTP_TOKEN = "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjI1NzkzMTIzMTAsImlhdCI6MTc5MDkxMjMxMCwibmJmIjoxNzkwOTEyMzEwLCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCJkM2JlZmNhNS1kOTk5LTQwYWYtOGU3Yi1jYTM2MzNkMDhlNmVcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiMmU1Zjg5NWQtMmRiNS00MGJjLTllZTYtOGM0Y2JmOGM3YjIwXCIsXCJkZXZpY2VJZFwiOlwiODk4ZGMwOTItNWIwYi01OWY4LWFhNWUtYzk5OGFmOTcwYWJhXCIsXCJzZXNzaW9uSWRcIjpcIjljY2U1MzM3LWFjN2QtNDJkMS1iYjYwLTNkM2E4MjgyYjQxMFwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYkpkbDlKZEo5NGpVblhOeEx2Y215Y1JSTkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcImF1dGgtdG90cFwiLFwic291cmNlSXBBZGRyZXNzXCI6XCIyMDMuMTEwLjI0Ny41MywxNzIuNjkuMTI5LjIyOCwzNS4yNDEuMjMuMTIzXCIsXCJ0d29GYUV4cGlyeVRzXCI6MjU3OTMxMjMxMDEzOSxcInZlbmRvck5hbWVcIjpcImdyb3d3QXBpXCJ9IiwiaXNzIjoiYXBleC1hdXRoLXByb2QtYXBwIn0.OAAWyAxr4ebZnOs7-g8G7FGIU7NziA2k7mj6YZ10NwDaPK5MHEt1CZkv558KZSz4iwXqcssEvy0Yc9PdWI7cug"
TOTP_SECRET = "XOSCLAKBD65O6RF5OPAHBWHJRPTYYLPQ"
SYMBOL = "RELIANCE"
QTY = 1  # start with 1 for testing

def login():
    code = pyotp.TOTP(TOTP_SECRET).now()
    token = GrowwAPI.get_access_token(api_key=TOTP_TOKEN, totp=code)
    return GrowwAPI(token)

groww = login()

# --- Helper to get LTP (needs paid plan) ---
def get_ltp(symbol):
    try:
        # This needs paid API, else it will error - that's ok for testing
        resp = groww.get_ltp(trading_symbol=symbol, exchange=groww.EXCHANGE_NSE)
        return float(resp['ltp'])
    except Exception as e:
        print(f"LTP failed (need paid plan): {e}")
        return None

# --- Simple state ---
in_position = False
buy_price = 0

print("Bot started - market hours 9:15 to 15:30")
while True:
    now = datetime.now()
    # Only trade during market hours
    if not (9 <= now.hour <= 15):
        time.sleep(60)
        continue

    ltp = get_ltp(SYMBOL)
    if ltp is None:
        # For Free Trial testing - simulate with holdings check
        print("No live price - checking holdings only")
        time.sleep(60)
        continue

    print(f"{now.strftime('%H:%M:%S')} {SYMBOL} LTP: {ltp}")

    # --- YOUR STRATEGY LOGIC HERE ---
    # Example: Replace this with RSI, Supertrend, VWAP etc.
    # For now: Simple breakout example
    # You should fetch historical candles and calculate EMA
    
    # BUY CONDITION - customize
    if not in_position and ltp > 0:  # put your condition like ema9 > ema21
        print(f"BUY SIGNAL {SYMBOL} @ {ltp}")
        # UNCOMMENT TO PLACE REAL ORDER - TEST WITH 1 QTY FIRST
        order = groww.place_order(
            trading_symbol=SYMBOL,
            quantity=QTY,
            validity=groww.VALIDITY_DAY,
            exchange=groww.EXCHANGE_NSE,
            segment=groww.SEGMENT_CASH,
            product=groww.PRODUCT_CNC,
            order_type=groww.ORDER_TYPE_MARKET,
            transaction_type=groww.TRANSACTION_TYPE_BUY,
            order_reference_id=f"buy-{int(time.time())}"
        )
        print(order)
        in_position = True
        buy_price = ltp

    # SELL CONDITION - with target/stop-loss
    if in_position:
        pnl_pct = (ltp - buy_price) / buy_price * 100
        # Exit if 2% profit or 1% loss or reversal signal
        if pnl_pct >= 2.0 or pnl_pct <= -1.0:
            print(f"SELL SIGNAL P&L {pnl_pct:.2f}%")
            groww.place_order(
                trading_symbol=SYMBOL,
                quantity=QTY,
                validity=groww.VALIDITY_DAY,
                exchange=groww.EXCHANGE_NSE,
                segment=groww.SEGMENT_CASH,
                product=groww.PRODUCT_CNC,
                order_type=groww.ORDER_TYPE_MARKET,
                transaction_type=groww.TRANSACTION_TYPE_SELL,
                order_reference_id=f"sell-{int(time.time())}"
            )
            in_position = False

    time.sleep(60)  # check every 60 sec - respects 300 req/min limit