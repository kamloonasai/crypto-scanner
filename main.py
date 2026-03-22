import requests
import time
import schedule
from datetime import datetime
import pytz

TELEGRAM_TOKEN   = "8769638447:AAHlzoSeo4IV2bhIEivA2kmeOiq5LoN4Z3k"
TELEGRAM_CHAT_ID = "8028512511"

SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT",
    "MATICUSDT","UNIUSDT","LTCUSDT","ATOMUSDT","NEARUSDT",
    "INJUSDT","SUIUSDT","OPUSDT","ARBUSDT","APTUSDT"
]

EMA_FAST  = 9
EMA_SLOW  = 21
EMA_TREND = 50
RSI_LEN   = 14
RSI_OB    = 70
RSI_OS    = 30
ATR_LEN   = 14
VOL_MULT  = 1.5
SL_ATR    = 1.5
TP1_ATR   = 2.0
TP2_ATR   = 3.5
INTERVAL  = "4h"

BKK = pytz.timezone("Asia/Bangkok")

def fetch_klines(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={INTERVAL}&limit=100"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data or len(data) < 60:
            return None
        opens   = [float(d[1]) for d in data]
        highs   = [float(d[2]) for d in data]
        lows    = [float(d[3]) for d in data]
        closes  = [float(d[4]) for d in data]
        volumes = [float(d[5]) for d in data]
        return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}
    except:
        return None

def calc_ema_array(data, period):
    k = 2 / (period + 1)
    emas = [data[0]]
    for i in range(1, len(data)):
        emas.append(data[i] * k + emas[-1] * (1 - k))
    return emas

def calc_rsi(closes, period):
    n = len(closes)
    gains = losses = 0
    for i in range(n - period - 1, n - 1):
        diff = closes[i+1] - closes[i]
        if diff > 0: gains += diff
        else: losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_atr(highs, lows, closes, period):
    n = len(closes)
    trs = []
    for i in range(n - period - 1, n):
        if i == 0: continue
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs) / len(trs)

def calc_macd(closes):
    ema12 = calc_ema_array(closes, 12)
    ema26 = calc_ema_array(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal_line = calc_ema_array(macd_line[26:], 9)
    return macd_line[-1], signal_line[-1]

def analyze_signal(klines):
    opens   = klines["opens"]
    highs   = klines["highs"]
    lows    = klines["lows"]
    closes  = klines["closes"]
    volumes = klines["volumes"]
    n = len(closes)

    ema9arr  = calc_ema_array(closes, EMA_FAST)
    ema21arr = calc_ema_array(closes, EMA_SLOW)
    ema50arr = calc_ema_array(closes, EMA_TREND)

    e9_now,  e9_prev  = ema9arr[n-2],  ema9arr[n-3]
    e21_now, e21_prev = ema21arr[n-2], ema21arr[n-3]
    e50_now           = ema50arr[n-2]

    close_now  = closes[n-2]
    open_now   = opens[n-2]
    open_prev  = opens[n-3]
    close_prev = closes[n-3]

    rsi = calc_rsi(closes[:n-1], RSI_LEN)
    atr = calc_atr(highs[:n-1], lows[:n-1], closes[:n-1], ATR_LEN)

    vol_avg = sum(volumes[n-21:n-1]) / 20
    vol_ok  = volumes[n-2] > vol_avg * VOL_MULT

    macd_last, signal_last = calc_macd(closes[:n-1])

    cross_up    = (e9_prev <= e21_prev) and (e9_now > e21_now)
    cross_down  = (e9_prev >= e21_prev) and (e9_now < e21_now)
    bull_trend  = (close_now > e50_now) and (e9_now > e50_now)
    bear_trend  = (close_now < e50_now) and (e9_now < e50_now)
    rsi_long    = 45 < rsi < RSI_OB
    rsi_short   = RSI_OS < rsi < 55
    bull_engulf = (close_now > open_now) and (close_now > open_prev) and (open_now < close_prev)
    bear_engulf = (close_now < open_now) and (close_now < open_prev) and (open_now > close_prev)
    macd_bull   = macd_last > signal_last
    macd_bear   = macd_last < signal_last

    long_signal  = cross_up   and bull_trend and rsi_long  and vol_ok and bull_engulf and macd_bull
    short_signal = cross_down and bear_trend and rsi_short and vol_ok and bear_engulf and macd_bear
    signal = "LONG" if long_signal else "SHORT" if short_signal else None

    return {
        "signal": signal,
        "price":  close_now,
        "rsi":    round(rsi, 1),
        "sl":     round(close_now - atr * SL_ATR,  6) if long_signal  else round(close_now + atr * SL_ATR,  6) if short_signal else None,
        "tp1":    round(close_now + atr * TP1_ATR, 6) if long_signal  else round(close_now - atr * TP1_ATR, 6) if short_signal else None,
        "tp2":    round(close_now + atr * TP2_ATR, 6) if long_signal  else round(close_now - atr * TP2_ATR, 6) if short_signal else None,
    }

def fmt(p):
    if p is None: return "-"
    if p >= 1000: return f"{p:.1f}"
    if p >= 1:    return f"{p:.3f}"
    return f"{p:.6f}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def scan_signals():
    now = datetime.now(BKK).strftime("%d/%m/%y %H:%M")
    print(f"\n[{now}] เริ่มสแกน {len(SYMBOLS)} เหรียญ...")

    long_signals  = []
    short_signals = []

    for symbol in SYMBOLS:
        try:
            klines = fetch_klines(symbol)
            if not klines:
                print(f"  ดึงข้อมูล {symbol} ไม่ได้")
                continue
            result = analyze_signal(klines)
            result["symbol"] = symbol.replace("USDT", "")
            if result["signal"] == "LONG":
                long_signals.append(result)
                print(f"  LONG  {symbol} @ {fmt(result['price'])}")
            elif result["signal"] == "SHORT":
                short_signals.append(result)
                print(f"  SHORT {symbol} @ {fmt(result['price'])}")
            else:
                print(f"  No signal — {symbol}")
            time.sleep(0.3)
        except Exception as e:
            print(f"  Error {symbol}: {e}")

    total = len(long_signals) + len(short_signals)
    if total == 0:
        print("ไม่พบสัญญาณในรอบนี้")
        return

    msg = f"🔔 <b>Crypto Signal Scanner</b>\n"
    msg += f"<b>TF: 4H</b> | {now} (BKK)\n"
    msg += "━━━━━━━━━━━━━━━━━\n"

    if long_signals:
        msg += f"\n🟢 <b>LONG ({len(long_signals)})</b>\n"
        for s in long_signals:
            msg += f"\n<b>{s['symbol']}/USDT</b>\n"
            msg += f"💰 Entry : <code>{fmt(s['price'])}</code>\n"
            msg += f"🛑 SL    : <code>{fmt(s['sl'])}</code>\n"
            msg += f"🎯 TP1   : <code>{fmt(s['tp1'])}</code>\n"
            msg += f"🎯 TP2   : <code>{fmt(s['tp2'])}</code>\n"
            msg += f"📊 RSI   : {s['rsi']}\n"

    if short_signals:
        msg += f"\n🔴 <b>SHORT ({len(short_signals)})</b>\n"
        for s in short_signals:
            msg += f"\n<b>{s['symbol']}/USDT</b>\n"
            msg += f"💰 Entry : <code>{fmt(s['price'])}</code>\n"
            msg += f"🛑 SL    : <code>{fmt(s['sl'])}</code>\n"
            msg += f"🎯 TP1   : <code>{fmt(s['tp1'])}</code>\n"
            msg += f"🎯 TP2   : <code>{fmt(s['tp2'])}</code>\n"
            msg += f"📊 RSI   : {s['rsi']}\n"

    msg += "\n━━━━━━━━━━━━━━━━━\n"
    msg += f"พบสัญญาณทั้งหมด {total} เหรียญ"

    send_telegram(msg)
    print(f"ส่ง Telegram เรียบร้อย — พบ {total} สัญญาณ")

if __name__ == "__main__":
    print("✅ Crypto Signal Bot เริ่มทำงาน!")
    send_telegram("✅ <b>Crypto Signal Bot เริ่มทำงานแล้ว!</b>\n\nสแกน 20 เหรียญทุก 4 ชั่วโมง\n⏰ 00:05 / 04:05 / 08:05 / 12:05 / 16:05 / 20:05 (เวลาไทย)")

    schedule.every().day.at("00:05").do(scan_signals)
    schedule.every().day.at("04:05").do(scan_signals)
    schedule.every().day.at("08:05").do(scan_signals)
    schedule.every().day.at("12:05").do(scan_signals)
    schedule.every().day.at("16:05").do(scan_signals)
    schedule.every().day.at("20:05").do(scan_signals)

    scan_signals()

    while True:
        schedule.run_pending()
        time.sleep(30)
