#!/usr/bin/env python3
"""
每日市場資料抓取腳本
由 GitHub Actions 每天 08:00（台灣時間）自動執行
結果存成 public/data.json 供 PWA 讀取
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ── 台灣時間 ──
TW = timezone(timedelta(hours=8))
now = datetime.now(TW)
today = now.strftime('%Y-%m-%d')
print(f"執行時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")

# ── 板塊個股定義 ──
SECTORS = [
    {"name": "半導體", "stocks": [
        {"symbol": "2330", "name": "台積電"},
        {"symbol": "2454", "name": "聯發科"},
        {"symbol": "2303", "name": "聯電"},
        {"symbol": "2379", "name": "瑞昱"},
        {"symbol": "3711", "name": "日月光"}
    ]},
    {"name": "電子", "stocks": [
        {"symbol": "2317", "name": "鴻海"},
        {"symbol": "2354", "name": "鴻準"},
        {"symbol": "2382", "name": "廣達"},
        {"symbol": "2308", "name": "台達電"},
        {"symbol": "2357", "name": "華碩"}
    ]},
    {"name": "金融", "stocks": [
        {"symbol": "2881", "name": "富邦金"},
        {"symbol": "2882", "name": "國泰金"},
        {"symbol": "2891", "name": "中信金"},
        {"symbol": "2886", "name": "兆豐金"},
        {"symbol": "2884", "name": "玉山金"}
    ]},
    {"name": "光電", "stocks": [
        {"symbol": "2409", "name": "友達"},
        {"symbol": "3481", "name": "群創"},
        {"symbol": "6669", "name": "緯穎"},
        {"symbol": "2498", "name": "宏達電"},
        {"symbol": "3673", "name": "TPK"}
    ]},
    {"name": "生技", "stocks": [
        {"symbol": "4763", "name": "台灣神隆"},
        {"symbol": "6547", "name": "聯合骨科"},
        {"symbol": "4726", "name": "永日"},
        {"symbol": "3707", "name": "漢磊"},
        {"symbol": "1795", "name": "美時"}
    ]},
]

# ── 指數代號 ──
INDICES = [
    {"key": "TWII", "symbol": "t00",  "name": "台股 TAIEX", "type": "INDEX"},
    {"key": "TSM",  "symbol": "2330", "name": "台積電",     "type": "STOCK"},
]


def fetch_with_sdk():
    """使用富邦 Neo SDK 抓取真實資料"""
    from fubon_neo.sdk import FubonSDK

    fubon_id      = os.environ["FUBON_ID"]
    fubon_pw      = os.environ["FUBON_PASSWORD"]
    fubon_cert_pw = os.environ["FUBON_CERT_PW"]

    sdk = FubonSDK()
    res = sdk.login(fubon_id, fubon_pw, fubon_cert_pw)
    if not res.is_success:
        raise RuntimeError(f"富邦登入失敗: {res.message}")
    print("✅ 富邦 Neo API 登入成功")

    sdk.init_realtime()
    rest = sdk.marketdata.rest_client.stock

    # ── 抓指數 ──
    indices_data = {}
    for idx in INDICES:
        try:
            if idx["type"] == "INDEX":
                d = rest.intraday.quote({"symbol": idx["symbol"], "type": "INDEX"})
            else:
                d = rest.intraday.quote({"symbol": idx["symbol"]})
            indices_data[idx["key"]] = {
                "name":    idx["name"],
                "symbol":  idx["symbol"],
                "price":   d.get("closePrice") or d.get("lastPrice") or 0,
                "change":  d.get("change", 0),
                "changePercent": d.get("changePercent", 0),
                "prev":    d.get("previousClose", 0),
            }
            print(f"  {idx['name']}: {indices_data[idx['key']]['price']} ({indices_data[idx['key']]['changePercent']:+.2f}%)")
        except Exception as e:
            print(f"  ⚠️  {idx['name']} 抓取失敗: {e}")
            indices_data[idx["key"]] = fallback_index(idx)

    # ── 抓板塊個股 ──
    sectors_data = []
    for sec in SECTORS:
        stocks_out = []
        for s in sec["stocks"]:
            try:
                d = rest.intraday.quote({"symbol": s["symbol"]})
                stocks_out.append({
                    "symbol": s["symbol"],
                    "name":   s["name"],
                    "price":  d.get("closePrice") or d.get("lastPrice") or 0,
                    "changePercent": d.get("changePercent", 0),
                })
            except Exception as e:
                print(f"  ⚠️  {s['name']} 失敗: {e}")
                stocks_out.append({"symbol": s["symbol"], "name": s["name"],
                                   "price": 0, "changePercent": 0})
        sectors_data.append({"name": sec["name"], "stocks": stocks_out})
        print(f"  板塊 {sec['name']} 完成")

    return indices_data, sectors_data


def fallback_index(idx):
    return {"name": idx["name"], "symbol": idx["symbol"],
            "price": 0, "change": 0, "changePercent": 0, "prev": 0}


def build_payload(indices_data, sectors_data, source):
    return {
        "date":    today,
        "updated": now.isoformat(),
        "source":  source,
        "indices": indices_data,
        "sectors": sectors_data,
    }


# ── 主流程 ──
source = "fubon_neo"
try:
    indices_data, sectors_data = fetch_with_sdk()
    print("✅ 富邦資料抓取完成")
except Exception as e:
    print(f"⚠️  富邦 SDK 失敗，使用占位資料: {e}")
    source = "fallback"
    indices_data = {
        idx["key"]: fallback_index(idx) for idx in INDICES
    }
    sectors_data = [
        {"name": sec["name"], "stocks": [
            {"symbol": s["symbol"], "name": s["name"],
             "price": 0, "changePercent": 0}
            for s in sec["stocks"]
        ]}
        for sec in SECTORS
    ]

payload = build_payload(indices_data, sectors_data, source)

os.makedirs("public", exist_ok=True)
with open("public/data.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print(f"\n✅ 寫入 public/data.json（來源：{source}）")
print(json.dumps(payload["indices"], ensure_ascii=False, indent=2))
