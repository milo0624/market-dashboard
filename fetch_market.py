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
    ]
    # 期貨
    fut_targets = [
        ("ES=F",  "ES",  "S&P 500 期貨"),
        ("NQ=F",  "NQ",  "那斯達克期貨"),
        ("NKD=F", "NKD", "日經期貨"),
        ("TWN=F", "TWN", "台指期"),
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

payload = {
    "date": today, "updated": now.isoformat(), "source": tw_source,
    "indices": indices,
    "futures": futures,
    "tw_sectors": tw_sectors,
    "sox_sectors": sox_sectors,
}

os.makedirs("public", exist_ok=True)
with open("public/data.json","w",encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"\n✅ 寫入完成（台股來源：{tw_source}）")
print(json.dumps({**indices, **{"期貨": futures}}, ensure_ascii=False, indent=2))
