#!/usr/bin/env python3
"""
抓台指期（近月連續）30 分 K 歷史資料 → txf_30m.csv，供 trading/backtest/box_sakata_30m.py 回測原始 Pine Script 策略。

只在 GitHub Actions「期貨分K下載」手動執行（沿用儀表板既有的富邦 Secrets），不影響每日排程。
富邦文件沒寫每次可抓幾天、分K能回溯多久，所以本程式會：
  1. 先用小區間試探 API 呼叫方式與回傳格式（全部印在 log，方便除錯）
  2. 從今天往回、每次抓一個區間，直到連續多段抓不到資料為止
"""
import base64, csv, json, os, sys, tempfile, time
from datetime import date, timedelta

PRODUCTS = os.environ.get("KBAR_PRODUCTS", "TXF,MXF,TMF").split(",")   # 依序嘗試，第一個成功的就用
TIMEFRAME = os.environ.get("KBAR_TIMEFRAME", "30")
EARLIEST = date.fromisoformat(os.environ.get("KBAR_EARLIEST", "2010-01-01"))
OUT = os.environ.get("KBAR_OUT", "txf_30m.csv")


def login():
    from fubon_neo.sdk import FubonSDK
    cert_b64 = os.environ["FUBON_CERT_B64"]
    cert_b64 += "=" * (-len(cert_b64) % 4)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
    tmp.write(base64.b64decode(cert_b64)); tmp.close()
    sdk = FubonSDK()
    res = sdk.apikey_login(os.environ["FUBON_ID"], os.environ["FUBON_API_KEY"], tmp.name, os.environ["FUBON_CERT_PW"])
    if not res.is_success:
        sys.exit(f"富邦登入失敗: {res.message}")
    sdk.init_realtime()
    print("✅ 富邦登入成功")
    return sdk.marketdata.rest_client.futopt


def rows_of(resp):
    """相容不同版本的回傳格式：dict{'data':[...]} 或直接 list"""
    if isinstance(resp, dict):
        data = resp.get("data") or resp.get("candles") or []
    else:
        data = resp or []
    out = []
    for r in data:
        t = r.get("date") or r.get("time") or r.get("datetime")
        if t is None:
            continue
        out.append({"datetime": str(t), "open": r["open"], "high": r["high"], "low": r["low"],
                    "close": r["close"], "volume": r.get("volume", 0)})
    return out


def call(rest, product, frm, to):
    params = {"symbol": product, "from": frm.isoformat(), "to": to.isoformat(), "timeframe": TIMEFRAME}
    return rest.historical.candles(**params)


def main():
    rest = login()

    # ── 1. 試探：哪個商品代號可用、回傳長什麼樣子 ──
    probe_to = date.today()
    probe_from = probe_to - timedelta(days=7)
    product = None
    for p in PRODUCTS:
        try:
            resp = call(rest, p, probe_from, probe_to)
            print(f"[試探] {p} 回傳（前 600 字）：{json.dumps(resp, ensure_ascii=False, default=str)[:600]}")
            if rows_of(resp):
                product = p
                break
        except Exception as e:
            print(f"[試探] {p} 失敗：{type(e).__name__}: {e}")
    if not product:
        sys.exit("所有商品代號都抓不到資料，請把上面的 log 貼給 Claude")
    print(f"➡️ 使用商品代號 {product}，timeframe={TIMEFRAME}")

    # ── 2. 找出單次可抓的最大天數（由大到小試）──
    span = None
    for days in (365, 180, 90, 60, 30, 14, 7):
        try:
            n = len(rows_of(call(rest, product, probe_to - timedelta(days=days), probe_to)))
            print(f"[區間] 一次抓 {days} 天 → {n} 根")
            if n:
                span = days
                break
        except Exception as e:
            print(f"[區間] 一次抓 {days} 天失敗：{type(e).__name__}: {e}")
    if not span:
        sys.exit("找不到可用的抓取區間")

    # ── 3. 從今天往回抓 ──
    allrows, to, empty_streak = {}, probe_to, 0
    while to > EARLIEST and empty_streak < 3:
        frm = max(EARLIEST, to - timedelta(days=span - 1))
        try:
            got = rows_of(call(rest, product, frm, to))
        except Exception as e:
            print(f"  {frm} ~ {to} 失敗：{e}；等 5 秒重試一次")
            time.sleep(5)
            try:
                got = rows_of(call(rest, product, frm, to))
            except Exception as e2:
                print(f"  重試仍失敗：{e2}")
                got = []
        for r in got:
            allrows[r["datetime"]] = r
        empty_streak = 0 if got else empty_streak + 1
        print(f"  {frm} ~ {to}：{len(got)} 根（累計 {len(allrows)}）")
        to = frm - timedelta(days=1)
        time.sleep(0.5)   # 避免打太快被限流

    rows = [allrows[k] for k in sorted(allrows)]
    if not rows:
        sys.exit("沒有抓到任何資料")
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["datetime", "open", "high", "low", "close", "volume"])
        w.writeheader(); w.writerows(rows)
    print(f"✅ {product} {TIMEFRAME} 分K：{rows[0]['datetime']} ～ {rows[-1]['datetime']}，共 {len(rows):,} 根 → {OUT}")


if __name__ == "__main__":
    main()
