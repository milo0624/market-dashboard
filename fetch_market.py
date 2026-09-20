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
        {"symbol":"2379","name":"瑞昂"}]},
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
        {"symbol":"6669","name":"緯飀"},{"symbol":"2409","name":"友達"},
        {"symbol":"3481","name":"群創"},{"symbol":"3673","name":"TPK"},
        {"symbol":"2498","name":"寏達電"}]},
]

SOX_SECTORS = [
    {"name":"晶片設計","stocks":[
        {"symbol":"NVDA","name":"輝達"},{"symbol":"AVGO","name":"博通"},
        {"symbol":"AMD","name":"超微"},{"symbol":"QCOM","name":"高通"},
        {"symbol":"MRVL","name":"邂威爾"}]},
    {"name":"設備材料","stocks":[
        {"symbol":"ASML","name":"艱司摩爾"},{"symbol":"AMAT","name":"應用材料"},
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

def load_watchlist():
    """讀取 watchlist.json（自選股清單）。檔案不存在或格式錯誤時回傳空清單，不影響其餘資料抓取。
    格式：{"stocks": [{"symbol":"2317","name":"鴻海","market":"TW"}, {"symbol":"AAPL","name":"蓹果","market":"US"}]}
    market 為 "TW" 時優先用富邦即時報價（Fubon 失敗則退回 Yahoo 的 <代號>.TW），其餘視為美股/其他市場一律用 Yahoo。"""
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        stocks = cfg.get("stocks", [])
        return [s for s in stocks if s.get("symbol")]
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"⚠️ 讀取 watchlist.json 失敗，自選股略過本次更新: {e}")
        return []

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
    """抓取每日 OHLCV（開高低收量 + 交易日日期），由舊到新排序，供策略計算與事後勝率追蹤使用"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={rng}"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    result = data["chart"]["result"][0]
    ts = result.get("timestamp", [])
    gmtoffset = result.get("meta", {}).get("gmtoffset", 0)
    q = result["indicators"]["quote"][0]
    bars = []
    for i in range(len(ts)):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c, v):
            continue
        date_str = datetime.fromtimestamp(ts[i] + gmtoffset, tz=timezone.utc).strftime('%Y-%m-%d')
        bars.append({"date": date_str, "open": o, "high": h, "low": l, "close": c, "volume": v})
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

def fetch_tw(watchlist_tw_symbols=None):
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

    tw_watch_quotes = {}
    if watchlist_tw_symbols:
        print("  [自選股-台股]")
        for sym in watchlist_tw_symbols:
            try:
                d = rest.intraday.quote(symbol=sym)
                tw_watch_quotes[sym] = {
                    "price": d.get("closePrice") or d.get("lastPrice") or 0,
                    "change": d.get("change", 0),
                    "changePercent": d.get("changePercent", 0),
                    "prev": d.get("previousClose", 0),
                }
                print(f"    {sym}: {tw_watch_quotes[sym]['price']} ({tw_watch_quotes[sym]['changePercent']:+.2f}%)")
            except Exception as e:
                print(f"    ⚠️ 自選股 {sym} 失敗: {e}")

    return tw_indices, tw_sectors, tw_watch_quotes

def fetch_institutional_futures():
    """抓取期交所官方 OpenAPI：三大法人-區分各期貨契約-依日期，取出「臺股期貨」（大台）未沖銷部位。
    來源：https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate
    （對應 data.gov.tw 資料集 11596，官方公開 API，非爬蟲，每日更新）。
    欄位名稱已由除錯探測版本確認（實際跑過 GitHub Actions 驗證），格式範例：
    {"Date":"20260918","ContractCode":"臺股期貨","Item":"自營商",
     "TradingVolume(Net)":"-2437","OpenInterest(Net)":"-3192",
     "ContractValueofOpenInterest(Net)(Thousands)":"-30271605", ...}
    這裡只取 ContractCode=="臺股期貨" 且 Item 為自營商／投信／外資 的三筆，算出各自與合計的未平倉淨口數。
    這一步失敗不影響其餘資料，會被上層 try/except 接住。"""
    url = "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    parsed = json.loads(raw)
    records = parsed if isinstance(parsed, list) else (
        parsed.get("data") or parsed.get("Data") or parsed.get("result") or []
    )
    if not records:
        raise RuntimeError(f"API 回應無資料筆數（頂層型別：{type(parsed).__name__}）")

    TARGET_CONTRACT = "臺股期貨"
    WANTED_ITEMS = ["自營商", "投信", "外資"]

    def to_int(v):
        try:
            return int(str(v).replace(",", ""))
        except Exception:
            return 0

    rows = [r for r in records if r.get("ContractCode") == TARGET_CONTRACT and r.get("Item") in WANTED_ITEMS]
    if not rows:
        raise RuntimeError(f"找不到「{TARGET_CONTRACT}」的三大法人資料（欄位或契約代碼可能已變動）")

    items = []
    total_net_oi = 0
    total_net_oi_value = 0
    for item_name in WANTED_ITEMS:
        row = next((r for r in rows if r.get("Item") == item_name), None)
        if not row:
            continue
        net_oi = to_int(row.get("OpenInterest(Net)"))
        net_oi_value = to_int(row.get("ContractValueofOpenInterest(Net)(Thousands)"))
        net_vol = to_int(row.get("TradingVolume(Net)"))
        items.append({"name": item_name, "netOi": net_oi, "netOiValue": net_oi_value, "netVol": net_vol})
        total_net_oi += net_oi
        total_net_oi_value += net_oi_value

    date_raw = rows[0].get("Date", "")
    date_fmt = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}" if len(str(date_raw)) == 8 else date_raw

    print(f"  三大法人臺股期貨未平倉（{date_fmt}）：合計淨 {total_net_oi} 口，明細：" +
          "、".join(f"{it['name']} {it['netOi']}口" for it in items))

    return {
        "date": date_fmt,
        "contract": TARGET_CONTRACT,
        "items": items,
        "totalNetOi": total_net_oi,
        "totalNetOiValue": total_net_oi_value,
    }

# ── 主流程 ──
print("\n📡 抓取全球指數 + 期貨（Yahoo Finance）...")
global_indices, futures = fetch_global()

print("\n📡 抓取貴金屬（Yahoo Finance）...")
metals = fetch_metals()

print("\n📡 抓取 SOX 個股 + 走勢（Yahoo Finance）...")
sox_sectors = fetch_sectors_with_trend(SOX_SECTORS, use_yahoo=True)

watchlist_cfg = load_watchlist()
watchlist_tw_syms = [w["symbol"] for w in watchlist_cfg if w.get("market", "US").upper() == "TW"]
if watchlist_cfg:
    print(f"\n📡 自選股清單：共 {len(watchlist_cfg)} 檔（台股 {len(watchlist_tw_syms)} 檔）")

print("\n📡 抓取台股（富邦 Neo API）+ 走勢（Yahoo Finance）...")
try:
    tw_indices, tw_sectors, tw_watch_quotes = fetch_tw(watchlist_tw_syms)
    tw_source = "fubon_neo"
except Exception as e:
    print(f"⚠️ 富邦 SDK 失敗: {e}")
    tw_source = "fallback"
    tw_indices = {"TSM":{"name":"台積電","symbol":"2330","price":0,"change":0,"changePercent":0,"prev":0}}
    tw_sectors = fetch_sectors_with_trend(TW_SECTORS, use_yahoo=True)
    tw_watch_quotes = {}
    if watchlist_tw_syms:
        print("  [自選股-台股 → 退回 Yahoo Finance]")
        for sym in watchlist_tw_syms:
            try:
                tw_watch_quotes[sym] = yahoo_quote(sym + ".TW")
            except Exception as e2:
                print(f"    ⚠️ 自選股 {sym} 失敗: {e2}")

indices = {**global_indices, **tw_indices}

# ── 自選股清單：台股用富邦即時（或上面的 Yahoo 退回），其餘市場一律用 Yahoo Finance ──
watchlist = []
if watchlist_cfg:
    print("\n📡 抓取自選股（其餘市場，Yahoo Finance）...")
for w in watchlist_cfg:
    sym = w["symbol"]
    name = w.get("name", sym)
    market = w.get("market", "US").upper()
    if market == "TW":
        q = tw_watch_quotes.get(sym)
    else:
        try:
            q = yahoo_quote(sym)
            print(f"    {name}({sym}): {q['price']} ({q['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"    ⚠️ 自選股 {name}({sym}) 失敗: {e}")
            q = None
    if not q:
        q = {"price": 0, "change": 0, "changePercent": 0, "prev": 0}
    watchlist.append({"symbol": sym, "name": name, "market": market, **q})

print("\n📡 抓取三大法人期貨未平倉（期交所 OpenAPI，臺股期貨）...")
try:
    inst_futures = fetch_institutional_futures()
except Exception as e:
    print(f"⚠️ 三大法人期貨資料抓取失敗（不影響其餘資料）: {e}")
    inst_futures = None

# ── 關鍵資料檢查：避免抓取失敗時仍以 0 覆蓋掉正確資料 ──
CRITICAL_INDEX_KEYS = ["TWII", "TSM_ADR", "SOX"]
CRITICAL_FUTURE_KEYS = ["ES"]
missing = [k for k in CRITICAL_INDEX_KEYS if indices.get(k, {}).get("price", 0) == 0]
missing += [f"期貨:{k}" for k in CRITICAL_FUTURE_KEYS if futures.get(k, {}).get("price", 0) == 0]
if missing:
    raise RuntimeError(f"關鍵資料抓取失敗，中止更新以避免用 0 覆蓋既有資料：{missing}")

# ── 訊號歷史紀錄（井田戰法 + 酒田戰法 + 成交量確認，對應原始 Pine Script 策略）──
def calc_pine_signal(bars):
    """
    移植自使用者的 Pine Script v5 策略（井田箱體突破 + 酒田K線型態 + 成交量確認），
    在每日 K 棒上執行「嚴格模式」：突破 + 量能 + 均線趨勢 + K 線型態需同時成立。
    bars：依時間由舊到新排序的 OHLCV 列表（至少需要61根）。
    回傳 (today_dir, detail)：today_dir 為 +1 多 / -1 空 / 0 中性；detail 為判斷細節。
    """
    LENGTH_BOX, MA_SHORT, MA_LONG, LENGTH_VOL, VOL_MULT = 20, 20, 60, 20, 1.2

    min_bars = max(LENGTH_BOX + 1, MA_LONG, LENGTH_VOL, 3) + 1
    if len(bars) < min_bars:
        raise RuntimeError(f"台指現貨(^TWII) 歷史K棒不足（需要至少 {min_bars} 根，實際 {len(bars)} 根），無法計算策略訊號")

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
        "symbol": "^TWII", "date": c["date"], "close": c["close"], "open": c["open"], "volume": c["volume"],
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

print("\n📡 抓取台指現貨(^TWII) 日K棒，計算井田+酒田+成交量策略訊號...")
try:
    twii_bars = yahoo_ohlcv("^TWII", rng="6mo")
    today_dir, signal_detail = calc_pine_signal(twii_bars)
    print(f"  策略訊號明細：{json.dumps(signal_detail, ensure_ascii=False)}")
except Exception as e:
    raise RuntimeError(f"策略訊號計算失敗，中止更新：{e}")

today_entry = {"date": today, "dir": today_dir}
if today_dir != 0:
    today_entry["closeAtSignal"] = signal_detail["close"]

# 更新今日紀錄（避免重複）
if history and history[-1]["date"] == today:
    history[-1] = today_entry
else:
    history.append(today_entry)

# 只保留最近 30 天
history = history[-30:]

# ── 事後勝率追蹤：訊號出現後，依「進場價 ±3%/6%」停損停盈規則模擬到 5 / 10 個交易日 ──
# 只針對「有 closeAtSignal」的訊號（即本次新策略上線後才產生的訊號）計分，
# 不回溯舊版（跨市場涨跌幅）策略留下的歷史紀錄，避免混淆勝率。
# 停損/停盈比例與前端顯示的建議規則一致（多單 -3%/+6%，空單 +3%/-6%）：
# 一旦期間內觸價就視為出場，不再像過去一樣硬等满5/10天才用收盤價計算，
# 避免像回測看到的「獲利在持有期間整個回吐」問題反映不到勝率數字上。
STOP_PCT, TARGET_PCT = 0.03, 0.06

def simulate_exit(bars, entry_idx, direction, entry_price, horizon):
    """從進場隔天起逐日檢查是否觸及停損/停盈，回傳 (exit_price, exit_kind)；
    若在 horizon 個交易日內都沒觸價，回傳 (None, 'horizon') 交由呼叫端取滿期收盤價。"""
    if direction > 0:
        stop_price, target_price = entry_price * (1 - STOP_PCT), entry_price * (1 + TARGET_PCT)
    else:
        stop_price, target_price = entry_price * (1 + STOP_PCT), entry_price * (1 - TARGET_PCT)
    for step in range(1, horizon + 1):
        idx = entry_idx + step
        if idx >= len(bars):
            break
        bar = bars[idx]
        stop_hit  = bar["low"] <= stop_price   if direction > 0 else bar["high"] >= stop_price
        target_hit = bar["high"] >= target_price if direction > 0 else bar["low"] <= target_price
        if stop_hit:
            return stop_price, "stop"  # 同一天觸及停損/停盈無法判斷先後順序，保守假設停損先發生
        if target_hit:
            return target_price, "target"
    return None, "horizon"

date_to_idx = {b["date"]: i for i, b in enumerate(twii_bars)}
for entry in history:
    if entry.get("dir", 0) == 0 or "closeAtSignal" not in entry:
        continue
    idx = date_to_idx.get(entry["date"])
    if idx is None:
        continue
    for horizon, key in ((5, "fwd5"), (10, "fwd10")):
        if key in entry or idx + horizon >= len(twii_bars):
            continue
        exit_price, exit_kind = simulate_exit(twii_bars, idx, entry["dir"], entry["closeAtSignal"], horizon)
        if exit_price is None:
            exit_price = twii_bars[idx + horizon]["close"]
        ret = round((exit_price - entry["closeAtSignal"]) / entry["closeAtSignal"] * 100, 2)
        hit = (entry["dir"] > 0 and ret > 0) or (entry["dir"] < 0 and ret < 0)
        entry[key] = {"ret": ret, "hit": hit, "exit": exit_kind}

def summarize_track_record(history, key):
    scored = [e[key] for e in history if key in e]
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    stopped = sum(1 for s in scored if s.get("exit") == "stop")
    targeted = sum(1 for s in scored if s.get("exit") == "target")
    return {"n": n, "hits": hits, "winRate": round(hits / n * 100, 1) if n else None,
            "stopped": stopped, "targeted": targeted}

track_record = {
    "fwd5": summarize_track_record(history, "fwd5"),
    "fwd10": summarize_track_record(history, "fwd10"),
}

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
    "track_record": track_record,  # 訊號出現後 5/10 個交易日的事後勝率（樣本僅計入新策略上線後的訊號）
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
    "watchlist": watchlist,
    "inst_futures": inst_futures,
}

os.makedirs("public", exist_ok=True)
with open("public/data.json","w",encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"\n✅ 寫入完成（台股來源：{tw_source}）")
print(json.dumps({**indices, **{"期貨": futures}}, ensure_ascii=False, indent=2))
