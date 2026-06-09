#!/usr/bin/env python3
import json, os, base64, tempfile, urllib.request
from datetime import datetime, timezone, timedelta

TW = timezone(timedelta(hours=8))
now = datetime.now(TW)
today = now.strftime('%Y-%m-%d')
print(f"執行時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")

SECTORS = [
    {"name":"半導體","stocks":[
        {"symbol":"2330","name":"台積電"},{"symbol":"2454","name":"聯發科"},
        {"symbol":"2303","name":"聯電"},{"symbol":"2379","name":"瑞昱"},
        {"symbol":"3711","name":"日月光"}]},
    {"name":"電子","stocks":[
        {"symbol":"2317","name":"鴻海"},{"symbol":"2382","name":"廣達"},
        {"symbol":"2308","name":"台達電"},{"symbol":"2354","name":"鴻準"},
        {"symbol":"2357","name":"華碩"}]},
    {"name":"金融","stocks":[
        {"symbol":"2881","name":"富邦金"},{"symbol":"2882","name":"國泰金"},
        {"symbol":"2891","name":"中信金"},{"symbol":"2886","name":"兆豐金"},
        {"symbol":"2884","name":"玉山金"}]},
    {"name":"光電","stocks":[
        {"symbol":"2409","name":"友達"},{"symbol":"3481","name":"群創"},
        {"symbol":"6669","name":"緯穎"},{"symbol":"2498","name":"宏達電"},
        {"symbol":"3673","name":"TPK"}]},
    {"name":"生技","stocks":[
        {"symbol":"1795","name":"美時"},{"symbol":"6472","name":"保瑞"},
        {"symbol":"6446","name":"藥華藥"},{"symbol":"4726","name":"永昕"},
        {"symbol":"6547","name":"聯合再生"}]},
]

def yahoo_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    meta = data["chart"]["result"][0]["meta"]
    price  = meta.get("regularMarketPrice", 0)
    prev   = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
    change = round(price - prev, 2)
    change_pct = round((change / prev * 100) if prev else 0, 2)
    return {"price": round(price, 2), "change": change,
            "changePercent": change_pct, "prev": round(prev, 2)}

def fetch_global():
    targets = [
        ("^SOX",  "SOX",     "費半 SOX"),
        ("^N225", "N225",    "日經 225"),
        ("TSM",   "TSM_ADR", "TSM ADR"),
        ("^TWII", "TWII",    "台股 TAIEX"),
    ]
    result = {}
    for symbol, key, name in targets:
        try:
            q = yahoo_quote(symbol)
            result[key] = {"name": name, "symbol": symbol, **q}
            print(f"  {name}: {q['price']} ({q['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"  ⚠️ {name} 失敗: {e}")
            result[key] = {"name":name,"symbol":symbol,"price":0,"change":0,"changePercent":0,"prev":0}
    return result

def fetch_tw():
    from fubon_neo.sdk import FubonSDK

    cert_b64 = os.environ["FUBON_CERT_B64"]
    cert_b64 += "=" * (4 - len(cert_b64) % 4)
    cert_data = base64.b64decode(cert_b64)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
    tmp.write(cert_data)
    tmp.close()
    cert_path = tmp.name

    sdk = FubonSDK()
    res = sdk.apikey_login(
        os.environ["FUBON_ID"],
        os.environ["FUBON_API_KEY"],
        cert_path,
        os.environ["FUBON_CERT_PW"]
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

    sectors = []
    for sec in SECTORS:
        stocks = []
        for s in sec["stocks"]:
            try:
                d = rest.intraday.quote(symbol=s["symbol"])
                stocks.append({
                    "symbol": s["symbol"], "name": s["name"],
                    "price": d.get("closePrice") or d.get("lastPrice") or 0,
                    "changePercent": d.get("changePercent", 0)
                })
            except Exception as e:
                print(f"  ⚠️ {s['name']} 失敗: {e}")
                stocks.append({"symbol":s["symbol"],"name":s["name"],"price":0,"changePercent":0})
        sectors.append({"name":sec["name"],"stocks":stocks})
        print(f"  板塊 {sec['name']} 完成")

    return tw_indices, sectors

print("\n📡 抓取全球指數（Yahoo Finance）...")
global_indices = fetch_global()

print("\n📡 抓取台股（富邦 Neo API）...")
try:
    tw_indices, sectors = fetch_tw()
    tw_source = "fubon_neo"
except Exception as e:
    print(f"⚠️ 富邦 SDK 失敗: {e}")
    tw_source = "fallback"
    tw_indices = {
        "TSM": {"name":"台積電","symbol":"2330","price":0,"change":0,"changePercent":0,"prev":0},
    }
    sectors = [{"name":sec["name"],"stocks":[
        {"symbol":s["symbol"],"name":s["name"],"price":0,"changePercent":0}
        for s in sec["stocks"]]} for sec in SECTORS]

indices = {**global_indices, **tw_indices}

payload = {
    "date": today, "updated": now.isoformat(),
    "source": tw_source, "indices": indices, "sectors": sectors
}

os.makedirs("public", exist_ok=True)
with open("public/data.json","w",encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print(f"\n✅ 寫入完成（台股來源：{tw_source}）")
print(json.dumps(indices, ensure_ascii=False, indent=2))
