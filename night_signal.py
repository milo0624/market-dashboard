#!/usr/bin/env python3
"""
今晚夜盤：策略 1f（只抱夜盤＋日K 60MA 過濾＋300 點停損＋連假不留倉）的每日判斷與紙上交易紀錄

排程：GitHub Actions「今晚夜盤判斷」每個交易日 14:05（台灣時間）
輸出：public/night_signal.json（今天的判斷）、public/night_history.json（每天的判斷＋隔天結算的紙上損益）
推播：有設定 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID 兩個 Secrets 時，送一則 Telegram 訊息

規則（與 trading/backtest/strategies.py 的 1f 相同）
  做：今天日盤收盤 > 最近 60 個交易日收盤平均，且下一個交易日距今 ≤ 4 天（不是連假前）
  進場：今晚夜盤 15:00 開盤買 1 口 TMF；停損：進場價 − 300 點；出場：下一個交易日 08:45 開盤
  口數：min(3,000 ÷ (300 × 10), 900,000 ÷ (收盤 × 10))，無條件捨去（依 trading/plan.md）
"""
import json, math, os, sys, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

import fetch_futures_kbars as K

TW = timezone(timedelta(hours=8))
MA_N, STOP_PTS, MULT = 60, 300, 10
RISK_NTD, NOTIONAL_CAP = 3000, 900_000
COST = 13 * 2 + 1 * 2 * MULT          # 手續費＋滑價（期交稅另依價格計）
SIG_FILE, HIST_FILE = "public/night_signal.json", "public/night_history.json"


def fetch_bars(rest):
    """抓近 130 天日盤＋近 10 天夜盤 30 分K；沿用 fetch_futures_kbars 的試探邏輯"""
    today = date.today()
    product = None
    for p in K.PRODUCTS:
        try:
            if K.rows_of(K.call(rest, p, today - timedelta(days=7), today)):
                product = p; break
        except Exception as e:
            print(f"[試探] {p} 失敗：{e}")
    if not product:
        sys.exit("抓不到台指期資料")
    K.EARLIEST = today - timedelta(days=130)
    span = K.find_span(rest, product, None, "日盤") or 30
    day = K.fetch_all(rest, product, None, span, "日盤")
    night = {}
    for extra in K.NIGHT_PARAM_CANDIDATES:
        try:
            got = K.rows_of(K.call(rest, product, today - timedelta(days=10), today, extra))
            if got and sum(K.is_night(r["datetime"]) for r in got) >= len(got) * 0.9:
                night = {r["datetime"]: r for r in got}; break
        except Exception as e:
            print(f"[夜盤試探] {extra} 失敗：{e}")
    return product, day, night


def twse_holidays():
    """證交所休市日；抓不到回傳 None（此時只以週末判斷連假）"""
    try:
        req = urllib.request.Request("https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            items = json.loads(r.read())
    except Exception as e:
        print(f"⚠️ 證交所休市日曆抓取失敗：{e}")
        return None
    out = set()
    for it in items:
        text = " ".join(str(v) for v in it.values())
        if ("最後交易日" in text or "開始交易" in text) and "放假" not in text:
            continue                      # 這些是「有交易」的特別日
        raw = str(it.get("Date") or it.get("date") or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        try:
            if len(digits) == 7:          # 民國 yyyMMdd
                out.add(date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7])))
            elif len(digits) == 8:
                out.add(date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])))
        except ValueError:
            pass
    print(f"證交所休市日 {len(out)} 天")
    return out


def next_trading_day(d, holidays):
    n = d + timedelta(days=1)
    while n.weekday() >= 5 or (holidays and n in holidays):
        n += timedelta(days=1)
    return n


def day_table(day_rows):
    """日盤 30 分K → {日期: (開, 收)}"""
    t = {}
    for k in sorted(day_rows):
        r = day_rows[k]; d = date.fromisoformat(k[:10])
        o, c = t.get(d, (r["open"], r["close"]))
        t[d] = (o, r["close"])
    return t


def score(entry_date, night_rows, days):
    """昨晚（或更早）的紙上交易：夜盤第一根開盤進場，停損 300 點，下一個交易日 08:45 開盤出場"""
    start = datetime.combine(entry_date, datetime.min.time()).replace(hour=15)
    nxt = [d for d in sorted(days) if d > entry_date]
    if not nxt:
        return None
    exit_day = nxt[0]
    bars = [night_rows[k] for k in sorted(night_rows)
            if start <= datetime.fromisoformat(k[:19]) < datetime.combine(exit_day, datetime.min.time()).replace(hour=8)]
    if not bars:
        return None
    e = bars[0]["open"]; stop = e - STOP_PTS
    px, how = None, "開盤出場"
    for j, b in enumerate(bars):
        if j > 0 and b["open"] <= stop:
            px, how = b["open"], "跳空停損"; break
        if b["low"] <= stop:
            px, how = stop, "停損"; break
    if px is None:
        o = days[exit_day][0]
        px, how = (o, "跳空停損") if o <= stop else (o, "開盤出場")
    tax = 0.00002 * (e + px) * MULT
    return {"entry": e, "exit": px, "points": round(px - e, 1), "pnl": round((px - e) * MULT - COST - tax),
            "how": how, "exitDay": exit_day.isoformat()}


def telegram(text):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("（未設定 Telegram Secrets，略過推播）"); return
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body), timeout=20)
        print("✅ Telegram 已推播")
    except Exception as e:
        print(f"⚠️ Telegram 推播失敗：{e}")


def main():
    rest = K.login()
    product, day_rows, night_rows = fetch_bars(rest)
    days = day_table(day_rows)
    today = datetime.now(TW).date()
    try:
        hist = json.load(open(HIST_FILE, encoding="utf-8"))
    except Exception:
        hist = []

    # ── 1. 結算之前「做」但還沒結果的紙上交易 ──
    for h in hist:
        if h.get("decision") == "做" and "result" not in h:
            r = score(date.fromisoformat(h["date"]), night_rows, days)
            if r:
                h["result"] = r

    # ── 2. 今天的判斷 ──
    holidays = twse_holidays()
    if today not in days:
        sig = {"date": today.isoformat(), "decision": "休市", "reasons": ["今天沒有日盤資料（休市或資料尚未更新）"]}
    else:
        closes = [days[d][1] for d in sorted(days) if d <= today][-MA_N:]
        close = closes[-1]
        if len(closes) < MA_N:
            sys.exit(f"日盤資料只有 {len(closes)} 天，不足 {MA_N} 天")
        ma = sum(closes) / MA_N
        nxt = next_trading_day(today, holidays)
        long_break = (nxt - today).days > 4
        lots = min(math.floor(RISK_NTD / (STOP_PTS * MULT)), math.floor(NOTIONAL_CAP / (close * MULT)))
        reasons = [f"日盤收盤 {close:,.0f} {'>' if close > ma else '≤'} 60 日均線 {ma:,.0f}（差 {(close / ma - 1) * 100:+.1f}%）",
                   f"下一個交易日 {nxt.isoformat()}（{'連假，不留倉' if long_break else '非連假'}）"
                   + ("" if holidays is not None else "；⚠️ 休市日曆抓取失敗，只以週末判斷")]
        go = close > ma and not long_break and lots >= 1
        if lots < 1:
            reasons.append("依交易計畫算出 0 口")
        sig = {"date": today.isoformat(), "decision": "做" if go else "不做", "reasons": reasons,
               "close": close, "ma60": round(ma, 1), "nextTradingDay": nxt.isoformat(), "lots": lots if go else 0,
               "stopPoints": STOP_PTS, "product": product,
               "plan": "今晚夜盤 15:00 開盤買進 TMF，進場價 − 300 點掛停損，隔天 08:45 開盤出場" if go else ""}
        hist = [h for h in hist if h["date"] != sig["date"]]
        hist.append({k: sig[k] for k in ("date", "decision", "close", "ma60")})

    done = [h["result"]["pnl"] for h in hist if "result" in h]
    sig["paper"] = {"trades": len(done), "wins": sum(p > 0 for p in done), "total": sum(done),
                    "since": hist[0]["date"] if hist else None}
    sig["updated"] = datetime.now(TW).isoformat(timespec="minutes")
    last = next((h for h in reversed(hist) if "result" in h), None)
    if last:
        sig["lastResult"] = {"date": last["date"], **last["result"]}

    os.makedirs("public", exist_ok=True)
    json.dump(sig, open(SIG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(hist[-400:], open(HIST_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(sig, ensure_ascii=False, indent=2))

    # ── 3. 推播 ──
    lines = [f"🌙 今晚夜盤（{sig['date']}）：{sig['decision']}"] + [f"・{r}" for r in sig["reasons"]]
    if sig.get("plan"):
        lines.append(f"・{sig['plan']}（{sig['lots']} 口，紙上交易）")
    if last and last["date"] != sig["date"]:
        r = last["result"]
        lines.append(f"昨晚紙上：{r['entry']:,.0f} → {r['exit']:,.0f}（{r['how']}）{r['pnl']:+,} 元")
    p = sig["paper"]
    if p["trades"]:
        lines.append(f"紙上累計 {p['trades']} 筆，勝 {p['wins']}，合計 {p['total']:+,} 元")
    telegram("\n".join(lines))


if __name__ == "__main__":
    main()
