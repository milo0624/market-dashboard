#!/usr/bin/env python3
import json, os, base64, tempfile, urllib.request
from datetime import datetime, timezone, timedelta

TW = timezone(timedelta(hours=8))
now = datetime.now(TW)
today = now.strftime('%Y-%m-%d')
print(f"執行時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")

TW_SECTORS = [
    {"name":"半導體","stocks":[
        {"symbol":"2330","name":"台積電"},{"symbol":"2454","name":"聯發科"},
        {"symbol":"3711","name":"日月光"},{"symbol":"2303","name":"聯電"},
        {"symbol":"2379","name":"瑞昱"}]},
    {"name":"電子","stocks":[
        {"symbol":"2317","name":"鴻海"},{"symbol":"2308","name":"台達電"},
        {"symbol":"2382","name":"廣達"},{"symbol":"2357","name":"華碩"},
        {"symbol":"2354","name":"鴻準"}]},
    {"name":"金融","stocks":[
        {"symbol":"2881","name":"富邦金"},{"symbol":"2882","name":"國泰金"},
        {"symbol":"2891","name":"中信金"},{"symbol":"2886","name":"兆豐金"},
        {"symbol":"2884","name":"玉山金"}]},
    {"name":"生技","stocks":[
        {"symbol":"1795","name":"美時"},{"symbol":"6472","name":"保瑞"},
        {"symbol":"6446","name":"藥華藥"},{"symbol":"4726","name":"永昕"},
        {"symbol":"6547","name":"聯合再生"}]},
    {"name":"光電","stocks":[
        {"symbol":"6669","name":"緯穎"},{"symbol":"2409","name":"友達"},
        {"symbol":"3481","name":"群創"},{"symbol":"3673","name":"TPK"},
        {"symbol":"2498","name":"宏達電"}]},
]

SOX_SECTORS = [
    {"name":"晶片設計","stocks":[
        {"symbol":"NVDA","name":"輝達"},{"symbol":"AVGO","name":"博通"},
        {"symbol":"AMD","name":"超微"},{"symbol":"QCOM","name":"高通"},
        {"symbol":"MRVL","name":"邁威爾"}]},
    {"name":"設備材料","stocks":[
        {"symbol":"ASML","name":"艾司摩爾"},{"symbol":"AMAT","name":"應用材料"},
        {"symbol":"LRCX","name":"拉姆研究"},{"symbol":"KLAC","name":"科磊"},
        {"symbol":"TER","name":"泰瑞達"}]},
    {"name":"類比IC","stocks":[
        {"symbol":"TXN","name":"德州儀器"},{"symbol":"ADI","name":"亞德諾"},
        {"symbol":"MCHP","name":"微芯科技"},{"symbol":"MPWR","name":"單體電源"},
        {"symbol":"SWKS","name":"思佳訊"}]},
    {"name":"記憶體","stocks":[
        {"symbol":"MU","name":"美光"},{"symbol":"NXPI","name":"恩智浦"},
        {"symbol":"ON","name":"安森美"},{"symbol":"WDC","name":"威騰"},
        {"symbol":"STM","name":"意法半導"}]},
    {"name":"晶圓代工","stocks":[
        {"symbol":"INTC","name":"英特爾"},{"symbol":"GFS","name":"格芯"},
        {"symbol":"UMC","name":"聯電ADR"},{"symbol":"ASX","name":"台積ADR"},
        {"symbol":"IFNNY","name":"英飛凌"}]},
]

def yahoo_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
    change = round(price - prev, 2)
    change_pct = round((change / prev * 100) if prev else 0, 2)
    return {"price": round(price,2), "change": change,
            "changePercent": change_pct, "prev": round(prev,2)}

def yahoo_history(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    closes = data["chart"]["result"][0]["indicators"]["quote"][0].get("close", [])
    closes = [c for c in closes if c is not None]
    if not closes: return []
    base = closes[0]
    return [round((c - base) / base * 100, 2) for c in closes]

def yahoo_ohlcv(symbol, rng="6mo"):
    """抓取每日 OHLCV（開高低收量），由舊到新排序，供策略計算使用"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={rng}"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    result = data["chart"]["result"][0]
    ts = result.get("timestamp", [])
    q = result["indicators"]["quote"][0]
    bars = []
    for i in range(len(ts)):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c, v):
            continue
        bars.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
    return bars

def sector_trend(symbols):
    all_series = []
    for sym in symbols:
        try:
            s = yahoo_history(sym)
            if s: all_series.append(s)
        except: pass
    if not all_series: return []
    min_len = min(len(s) for s in all_series)
    return [round(sum(s[i] for s in all_series) / len(all_series), 2)
            for i in range(min_len)]

def fetch_global():
    # 指數
    idx_targets = [
        ("^SOX",  "SOX",     "費半 SOX"),
        ("^N225", "N225",    "日經 225"),
        ("TSM",   "TSM_ADR", "TSM ADR"),
        ("^TWII", "TWII",    "台股 TAIEX"),
        ("NVDA",  "NVDA",    "輝達 NVDA"),
        ("^VIX",  "VIX",     "VIX 恐慌"),
    ]
    # 期貨
    fut_targets = [
        ("ES=F",  "ES",  "S&P 500 期貨"),
        ("NQ=F",  "NQ",  "那斯達克期貨"),
        ("NKD=F", "NKD", "日經期貨"),
        ("EWT",   "TWN", "台指ETF(EWT)"),
    ]

    indices = {}
    print("  [指數]")
    for symbol, key, name in idx_targets:
        try:
            q = yahoo_quote(symbol)
            indices[key] = {"name": name, "symbol": symbol, **q}
            print(f"    {name}: {q['price']} ({q['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"    ⚠️ {name} 失敗: {e}")
            indices[key] = {"name":name,"symbol":symbol,"price":0,"change":0,"changePercent":0,"prev":0}

    futures = {}
    print("  [期貨]")
    for symbol, key, name in fut_targets:
        try:
            q = yahoo_quote(symbol)
            futures[key] = {"name": name, "symbol": symbol, **q}
            print(f"    {name}: {q['price']} ({q['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"    ⚠️ {name} 失敗: {e}")
            futures[key] = {"name":name,"symbol":symbol,"price":0,"change":0,"changePercent":0,"prev":0}

    return indices, futures

def fetch_metals():
    metals_targets = [
        ("GC=F", "GOLD", "黃金"),
        ("SI=F", "SILVER", "白銀"),
    ]
    metals = {}
    print("  [貴金屬]")
    for symbol, key, name in metals_targets:
        try:
            q = yahoo_quote(symbol)
            metals[key] = {"name": name, "symbol": symbol, **q}
            print(f"    {name}: {q['price']} ({q['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"    ⚠️ {name} 失敗: {e}")
            metals[key] = {"name":name,"symbol":symbol,"price":0,"change":0,"changePercent":0,"prev":0}
    return metals

def fetch_sectors_with_trend(sector_list, use_yahoo=False, rest=None):
    result = []
    for sec in sector_list:
        stocks = []
        for s in sec["stocks"]:
            try:
                if use_yahoo:
                    q = yahoo_quote(s["symbol"])
                    stocks.append({"symbol":s["symbol"],"name":s["name"],
                        "price":q["price"],"changePercent":q["changePercent"]})
                else:
                    d = rest.intraday.quote(symbol=s["symbol"])
                    stocks.append({"symbol":s["symbol"],"name":s["name"],
                        "price": d.get("closePrice") or d.get("lastPrice") or 0,
                        "changePercent": d.get("changePercent", 0)})
            except Exception as e:
                print(f"  ⚠️ {s['name']} 失敗: {e}")
                stocks.append({"symbol":s["symbol"],"name":s["name"],"price":0,"changePercent":0})

        print(f"  計算 {sec['name']} 板塊走勢...")
        trend_syms = [s["symbol"] for s in sec["stocks"]] if use_yahoo \
                     else [s["symbol"]+".TW" for s in sec["stocks"]]
        trend = sector_trend(trend_syms)
        result.append({"name":sec["name"],"stocks":stocks,"trend":trend})
        print(f"  {sec['name']} 完成（走勢{len(trend)}點）")
    return result

def fetch_tw():
    from fubon_neo.sdk import FubonSDK
    cert_b64 = os.environ["FUBON_CERT_B64"]
    cert_b64 += "=" * (4 - len(cert_b64) % 4)
    cert_data = base64.b64decode(cert_b64)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
    tmp.write(cert_data); tmp.close()

    sdk = FubonSDK()
    res = sdk.apikey_login(
        os.environ["FUBON_ID"], os.environ["FUBON_API_KEY"],
        tmp.name, os.environ["FUBON_CERT_PW"]
    )
    if not res.is_success:
        raise RuntimeError(f"富邦登入失敗: {res.message}")
    print("✅ 富邦登入成功")
    sdk.init_realtime()
    rest = sdk.marketdata.rest_client.stock

    tw_indices = {}
    for sym, key, name in [("2330","TSM","台積電")]:
        try:
            d = rest.intraday.quote(symbol=sym)
            tw_indices[key] = {
                "name": name, "symbol": sym,
                "price": d.get("closePrice") or d.get("lastPrice") or 0,
                "change": d.get("change", 0),
                "changePercent": d.get("changePercent", 0),
                "prev": d.get("previousClose", 0),
            }
            print(f"  {name}: {tw_indices[key]['price']} ({tw_indices[key]['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"  ⚠️ {name} 失敗: {e}")
            tw_indices[key] = {"name":name,"symbol":sym,"price":0,"change":0,"changePercent":0,"prev":0}

    tw_sectors = fetch_sectors_with_trend(TW_SECTORS, use_yahoo=False, rest=rest)
    return tw_indices, tw_sectors

# ── 主流程 ──
print("\n📡 抓取全球指數 + 期貨（Yahoo Finance）...")
global_indices, futures = fetch_global()

print("\n📡 抓取貴金屬（Yahoo Finance）...")
metals = fetch_metals()

print("\n📡 抓取 SOX 個股 + 走勢（Yahoo Finance）...")
sox_sectors = fetch_sectors_with_trend(SOX_SECTORS, use_yahoo=True)

print("\n📡 抓取台股（富邦 Neo API）+ 走勢（Yahoo Finance）...")
try:
    tw_indices, tw_sectors = fetch_tw()
    tw_source = "fubon_neo"
except Exception as e:
    print(f"⚠️ 富邦 SDK 失敗: {e}")
    tw_source = "fallback"
    tw_indices = {"TSM":{"name":"台積電","symbol":"2330","price":0,"change":0,"changePercent":0,"prev":0}}
    tw_sectors = fetch_sectors_with_trend(TW_SECTORS, use_yahoo=True)

indices = {**global_indices, **tw_indices}

# ── 關鍵資料檢查：避免抓取失敗時仍以 0 覆蓋掉正確資料 ──
CRITICAL_INDEX_KEYS = ["TWII", "TSM_ADR", "SOX"]
CRITICAL_FUTURE_KEYS = ["ES", "TWN"]
missing = [k for k in CRITICAL_INDEX_KEYS if indices.get(k, {}).get("price", 0) == 0]
missing += [f"期貨:{k}" for k in CRITICAL_FUTURE_KEYS if futures.get(k, {}).get("price", 0) == 0]
if missing:
    raise RuntimeError(f"關鍵資料抓取失敗，中止更新以避免用 0 覆蓋既有資料：{missing}")

# ── 訊號歷史紀錄（井田戰法 + 酒田戰法 + 成交量確認，對應原始 Pine Script 策略）──
def calc_pine_signal(bars):
    """
    移植自使用者的 Pine Script v5 策略（井田箱體突破 + 酒田K線型態 + 成交量確認），
    在每日 K 棒上執行「嚴格模式」：突破 + 量能 + 均線趨勢 + K 線型態需同時成立。
    bars：依時間由舊到新排序的 OHLCV 列表（至少需要 61 根）。
    回傳 (today_dir, detail)：today_dir 為 +1 多 / -1 空 / 0 中性；detail 為判斷細節。
    """
    LENGTH_BOX, MA_SHORT, MA_LONG, LENGTH_VOL, VOL_MULT = 20, 20, 60, 20, 1.5

    min_bars = max(LENGTH_BOX + 1, MA_LONG, LENGTH_VOL, 3) + 1
    if len(bars) < min_bars:
        raise RuntimeError(f"EWT 歷史K棒不足（需要至少 {min_bars} 根，實際 {len(bars)} 根），無法計算策略訊號")

    c, p1, p2 = bars[-1], bars[-2], bars[-3]
    closes  = [b["close"]  for b in bars]
    volumes = [b["volume"] for b in bars]

    box_bars = bars[-(LENGTH_BOX + 1):-1]  # 箱體不含當前K棒，對應 Pine 的 high[1]/low[1]
    highest_high = max(b["high"] for b in box_bars)
    lowest_low   = min(b["low"]  for b in box_bars)

    ma20 = sum(closes[-MA_SHORT:]) / MA_SHORT
    ma60 = sum(closes[-MA_LONG:]) / MA_LONG
    avg_vol = sum(volumes[-LENGTH_VOL:]) / LENGTH_VOL

    bull_vol = c["close"] > c["open"] and c["volume"] > avg_vol * VOL_MULT
    bear_vol = c["close"] < c["open"] and c["volume"] > avg_vol * VOL_MULT

    bull_trend = c["close"] > ma20 and ma20 > ma60
    bear_trend = c["close"] < ma20 and ma20 < ma60

    long_breakout  = c["close"] > highest_high
    short_breakout = c["close"] < lowest_low

    def is_doji(b):
        return abs(b["close"] - b["open"]) <= (b["high"] - b["low"]) * 0.1

    def is_small_body(b):
        return abs(b["open"] - b["close"]) <= (b["high"] - b["low"]) * 0.3

    bull_engulf = (c["close"] > c["open"] and p1["close"] < p1["open"]
                   and c["close"] >= p1["open"] and c["open"] <= p1["close"])
    bear_engulf = (c["close"] < c["open"] and p1["close"] > p1["open"]
                   and c["close"] <= p1["open"] and c["open"] >= p1["close"])

    morning_star = (p2["close"] < p2["open"] and is_doji(p1) and is_small_body(p1)
                     and c["close"] > (p2["open"] + p2["close"]) / 2)
    evening_star = (p2["close"] > p2["open"] and is_doji(p1) and is_small_body(p1)
                     and c["close"] < (p2["open"] + p2["close"]) / 2)

    long_confirm  = long_breakout  and bull_vol and bull_trend and (bull_engulf or morning_star)
    short_confirm = short_breakout and bear_vol and bear_trend and (bear_engulf or evening_star)

    today_dir = 1 if long_confirm else (-1 if short_confirm else 0)

    detail = {
        "symbol": "EWT", "close": c["close"], "open": c["open"], "volume": c["volume"],
        "avgVol": round(avg_vol, 0), "highestHigh": round(highest_high, 2), "lowestLow": round(lowest_low, 2),
        "ma20": round(ma20, 2), "ma60": round(ma60, 2),
        "longBreakout": long_breakout, "shortBreakout": short_breakout,
        "bullVol": bull_vol, "bearVol": bear_vol,
        "bullTrend": bull_trend, "bearTrend": bear_trend,
        "bullEngulf": bull_engulf, "bearEngulf": bear_engulf,
        "morningStar": morning_star, "eveningStar": evening_star,
    }
    return today_dir, detail

HISTORY_FILE = "public/signal_history.json"
try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
except:
    history = []

print("\n📡 抓取 EWT 日K棒，計算井田+酒田+成交量策略訊號...")
try:
    ewt_bars = yahoo_ohlcv("EWT", rng="6mo")
    today_dir, signal_detail = calc_pine_signal(ewt_bars)
    print(f"  策略訊號明細：{json.dumps(signal_detail, ensure_ascii=False)}")
except Exception as e:
    raise RuntimeError(f"策略訊號計算失敗，中止更新：{e}")

today_entry = {"date": today, "dir": today_dir}

# 更新今日紀錄（避免重複）
if history and history[-1]["date"] == today:
    history[-1] = today_entry
else:
    history.append(today_entry)

# 只保留最近 30 天
history = history[-30:]

# 計算連續訊號天數
streak = 0
streak_dir = today_dir
if today_dir != 0:
    for entry in reversed(history):
        if entry["dir"] == today_dir:
            streak += 1
        else:
            break

signal_meta = {
    "today_dir": today_dir,
    "streak": streak,
    "streak_dir": streak_dir,
    "history": history[-10:],  # 最近10天給前端顯示
    "detail": signal_detail,   # 井田+酒田+成交量策略的判斷明細（供前端顯示）
}

with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)
print(f"✅ 訊號歷史更新：今日方向={today_dir}，連續{streak}天")

payload = {
    "date": today, "updated": now.isoformat(), "source": tw_source,
    "indices": indices,
    "futures": futures,
    "metals": metals,
    "signal_meta": signal_meta,
    "tw_sectors": tw_sectors,
    "sox_sectors": sox_sectors,
}

os.makedirs("public", exist_ok=True)
with open("public/data.json","w",encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"\n✅ 寫入完成（台股來源：{tw_source}）")
print(json.dumps({**indices, **{"期貨": futures}}, ensure_ascii=False, indent=2))
