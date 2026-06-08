#!/usr/bin/env python3
import json, os, base64, tempfile
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
        {"symbol":"4763","name":"台灣神隆"},{"symbol":"6547","name":"聯合骨科"},
        {"symbol":"4726","name":"永日"},{"symbol":"3707","name":"漢磊"},
        {"symbol":"1795","name":"美時"}]},
]

def fetch():
    from fubon_neo.sdk import FubonSDK

    cert_b64 = os.environ["FUBON_CERT_B64"]
    cert_data = base64.b64decode(cert_b64)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
    tmp.write(cert_data)
    tmp.close()
    cert_path = tmp.name
    print(f"✅ 憑證還原至：{cert_path}")

    personal_id = os.environ["FUBON_ID"]
    api_key     = os.environ["FUBON_API_KEY"]
    cert_pw     = os.environ["FUBON_CERT_PW"]

    sdk = FubonSDK()
    res = sdk.apikey_login(personal_id, api_key, cert_path, cert_pw)
    if not res.is_success:
        raise RuntimeError(f"富邦登入失敗: {res.message}")
    print("✅ 富邦 API Key 登入成功")

    sdk.init_realtime()
    rest = sdk.marketdata.rest_client.stock

    indices = {}
    for sym, key, name, is_index in [
        ("2330","TSM","台積電", False),
        ("t00","TWII","台股 TAIEX", True)
    ]:
        try:
            d = rest.intraday.quote({"symbol":sym,"type":"INDEX"}) if is_index \
                else rest.intraday.quote({"symbol":sym})
            indices[key] = {
                "name": name, "symbol": sym,
                "price": d.get("closePrice") or d.get("lastPrice") or 0,
                "change": d.get("change", 0),
                "changePercent": d.get("changePercent", 0),
                "prev": d.get("previousClose", 0),
            }
            print(f"  {name}: {indices[key]['price']} ({indices[key]['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"  ⚠️ {name} 失敗: {e}")
            indices[key] = {"name":name,"symbol":sym,"price":0,"change":0,"changePercent":0,"prev":0}

    sectors = []
    for sec in SECTORS:
        stocks = []
        for s in sec["stocks"]:
            try:
                d = rest.intraday.quote({"symbol": s["symbol"]})
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

    return indices, sectors

try:
    indices, sectors = fetch()
    source = "fubon_neo"
except Exception as e:
    print(f"⚠️ 富邦 SDK 失敗，使用占位資料: {e}")
    sour
