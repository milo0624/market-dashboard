#!/usr/bin/env python3
"""
抓每個月「月選擇權結算」前後的期交所官方資料 → 結算日效應研究（trading/backtest/settlement.py）

輸出（GitHub Actions「結算資料下載」附件）
  settle_fut.csv  台指期(TX) 到期月契約每日：日期、到期月份、收盤價、結算價（到期日當天的結算價＝最後結算價）
  settle_oi.csv   臺指選擇權(TXO) 到期月契約每日：日期、到期月份、履約價、買賣權、未沖銷契約數
只保留「當月到期」的那個月契約、一般交易時段；每月只抓第三個星期三前 10 天～後 6 天，檔案很小。
資料來源：期交所「期貨／選擇權每日交易行情下載」(CSV, cp950)
"""
import csv, io, os, sys, time, urllib.parse, urllib.request
from datetime import date, timedelta

START = date.fromisoformat(os.environ.get("SETTLE_START", "2010-01-01"))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Content-Type": "application/x-www-form-urlencoded"}
EP = {"TX": "https://www.taifex.com.tw/cht/3/futDataDown", "TXO": "https://www.taifex.com.tw/cht/3/optDataDown"}


def third_wed(y, m):
    d = date(y, m, 1)
    d += timedelta(days=(2 - d.weekday()) % 7)
    return d + timedelta(days=14)


def download(prod, frm, to):
    body = urllib.parse.urlencode({"down_type": "1", "commodity_id": prod, "commodity_id2": "",
                                   "queryStartDate": frm.strftime("%Y/%m/%d"), "queryEndDate": to.strftime("%Y/%m/%d")}).encode()
    req = urllib.request.Request(EP[prod], data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    text = raw.decode("cp950", errors="replace")
    if "<html" in text[:500].lower():
        raise RuntimeError("回傳的是網頁不是 CSV：" + " ".join(text[:300].split()))
    return list(csv.reader(io.StringIO(text)))


def col(header, *keys):
    for i, h in enumerate(header):
        if all(k in h for k in keys):
            return i
    raise KeyError(f"找不到欄位 {keys}；表頭＝{header}")


def num(s):
    s = (s or "").strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def main():
    fut_rows, oi_rows, failed = [], [], []
    y, m = START.year, START.month
    today = date.today()
    first = True
    while date(y, m, 1) <= today:
        ym = f"{y}{m:02d}"
        tw = third_wed(y, m)
        frm, to = tw - timedelta(days=10), min(tw + timedelta(days=6), today)
        for prod in ("TX", "TXO"):
            try:
                rows = download(prod, frm, to)
            except Exception as e:
                print(f"  {ym} {prod} 失敗：{e}；5 秒後重試")
                time.sleep(5)
                try:
                    rows = download(prod, frm, to)
                except Exception as e2:
                    print(f"  {ym} {prod} 重試仍失敗：{e2}")
                    failed.append(f"{ym}-{prod}")
                    continue
            if not rows:
                failed.append(f"{ym}-{prod}"); continue
            hdr = [h.strip() for h in rows[0]]
            if first:
                print(f"[表頭 {prod}] {hdr}"); print(f"[範例 {prod}] {rows[1] if len(rows) > 1 else '（無資料）'}")
            iD, iC, iM = col(hdr, "日期"), col(hdr, "契約"), col(hdr, "到期月份")
            iS = next((i for i, h in enumerate(hdr) if "交易時段" in h), None)
            kept = 0
            for r in rows[1:]:
                if len(r) < len(hdr) - 2:
                    continue
                r = [x.strip() for x in r]
                if r[iC] != prod or r[iM] != ym:
                    continue
                if iS is not None and r[iS] and "一般" not in r[iS]:
                    continue
                d = r[iD].replace("/", "-")
                if prod == "TX":
                    fut_rows.append({"date": d, "month": ym, "close": num(r[col(hdr, "收盤價")]),
                                     "settle": num(r[col(hdr, "結算價")])})
                else:
                    oi = num(r[col(hdr, "未沖銷")])
                    if oi:
                        oi_rows.append({"date": d, "month": ym, "strike": num(r[col(hdr, "履約價")]),
                                        "cp": "C" if "買" in r[col(hdr, "買賣權")] else "P", "oi": int(oi)})
                kept += 1
            print(f"  {ym} {prod} {frm}～{to}：保留 {kept} 列")
            time.sleep(1.5)   # 期交所對頻繁下載很敏感，放慢
        first = False
        m += 1
        if m == 13:
            y, m = y + 1, 1

    with open("settle_fut.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "month", "close", "settle"]); w.writeheader(); w.writerows(fut_rows)
    with open("settle_oi.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "month", "strike", "cp", "oi"]); w.writeheader(); w.writerows(oi_rows)
    print(f"✅ 期貨 {len(fut_rows)} 列、選擇權 {len(oi_rows)} 列；失敗 {len(failed)} 個：{failed[:20]}")
    if not fut_rows or not oi_rows:
        sys.exit("沒有抓到資料，請把 log 貼給 Claude")


if __name__ == "__main__":
    main()
