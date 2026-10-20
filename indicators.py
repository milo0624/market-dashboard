#!/usr/bin/env python3
"""
輔助指標（概念參考 PatrickSUDO/fadacai-portfolio 的 rule_stats.py / fetch_leading.py，改寫為本專案用）：
  1. 策略勝率的統計判讀：巧合機率（丟銅板也能達成的機率）、同段行情去重、多空 regime 分組
  2. 市場寬度：成分股站上 50 日均線的比例 + 與指數的背離
  3. 恐慌溫度計：VIX / VIX3M 期限結構、美國高收益債信用利差（FRED，免金鑰）
  4. 台股月營收：YoY 連 2 月走升（加速）/ 由正轉負（需求轉弱）

全部為「顯示用」指標，不改變策略訊號本身；任一區塊失敗只影響該區塊，不中止整體更新。
"""
import csv, io, json, math, re, ssl, urllib.request
from datetime import datetime, timedelta

UA = {"User-Agent": "Mozilla/5.0"}


def http_get(url, timeout=30, ctx=None, headers=UA):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


# ── 1. 策略勝率統計判讀 ──────────────────────────────────────────────────────
VERIFIED_P, SUPPORT_P, MIN_INDEP = 0.05, 0.25, 5
REGIME_LOOKBACK = 21  # 過去 21 個交易日報酬 ≥0 → 多頭（up），否則空頭（down）


def binom_tail(k, n, p=0.5):
    """n 次裡至少猜對 k 次、而每次都是丟銅板（p=0.5）的機率"""
    if n == 0:
        return None
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def regime_at(bars, idx):
    if idx is None or idx < REGIME_LOOKBACK:
        return None
    return "up" if bars[idx]["close"] >= bars[idx - REGIME_LOOKBACK]["close"] else "down"


def _gap_days(a, b, date_to_idx):
    """兩個訊號之間相隔幾個交易日；超出 K 棒範圍時以日曆日 ×5/7 估算"""
    ia, ib = date_to_idx.get(a), date_to_idx.get(b)
    if ia is not None and ib is not None:
        return ib - ia
    da, db = datetime.strptime(a, "%Y-%m-%d"), datetime.strptime(b, "%Y-%m-%d")
    return round((db - da).days * 5 / 7)


def track_stats(history, key, horizon, date_to_idx):
    """
    history 內已計分（有 key 欄位）的訊號 → 勝率統計。
    同方向、且與前一個訊號相隔 ≤ horizon 個交易日的訊號，視為同一段行情（只取第一筆計分），
    避免連續幾天的訊號同漲同跌、把勝率灌水。
    """
    scored = [e for e in history if key in e]
    indep, prev = [], None
    for e in scored:
        same_run = (prev is not None and prev["dir"] == e["dir"]
                    and _gap_days(prev["date"], e["date"], date_to_idx) <= horizon)
        if not same_run:
            indep.append(e)
        prev = e

    n, k = len(indep), sum(1 for e in indep if e[key]["hit"])
    p = binom_tail(k, n)
    if n == 0:
        status = "none"
    elif n < MIN_INDEP:
        status = "insufficient"
    elif p <= VERIFIED_P:
        status = "verified"
    elif p <= SUPPORT_P:
        status = "support"
    elif binom_tail(n - k, n) <= SUPPORT_P:
        status = "inverse"  # 猜錯的次數多到不像運氣：策略可能反向
    else:
        status = "unverified"

    by_regime = {}
    for rg in ("up", "down"):
        sub = [e for e in indep if e.get("regime") == rg]
        by_regime[rg] = {"n": len(sub), "hits": sum(1 for e in sub if e[key]["hit"])}

    return {
        "rawN": len(scored), "rawHits": sum(1 for e in scored if e[key]["hit"]),
        "n": n, "hits": k,
        "winRate": round(k / n * 100, 1) if n else None,
        "pChance": round(p * 100, 1) if p is not None else None,
        "status": status,
        "byRegime": by_regime,
        "stopped": sum(1 for e in indep if e[key].get("exit") == "stop"),
        "targeted": sum(1 for e in indep if e[key].get("exit") == "target"),
    }


# ── 2. 市場寬度 ─────────────────────────────────────────────────────────────
DMA, BREADTH_DAYS = 50, 20


def _above_series(closes, days):
    """最近 days 個交易日，每天收盤是否站上當日的 50 日均線（資料不足回 None）"""
    if len(closes) < DMA + days - 1:
        return None
    out = []
    for end in range(len(closes) - days + 1, len(closes) + 1):
        window = closes[end - DMA:end]
        out.append(window[-1] > sum(window) / DMA)
    return out


def calc_breadth(sectors, closes_by_symbol, index_closes):
    """
    sectors: [{"name", "stocks":[{"symbol"}]}]；closes_by_symbol: symbol → 收盤序列（舊→新）
    回傳今日站上 50MA 比例、近 20 日比例走勢、各板塊明細，以及「指數創高但寬度轉弱」的背離旗標。
    """
    per_stock = {}
    for sec in sectors:
        for s in sec["stocks"]:
            ser = _above_series(closes_by_symbol.get(s["symbol"]) or [], BREADTH_DAYS)
            if ser:
                per_stock[s["symbol"]] = ser
    if not per_stock:
        raise RuntimeError("無足夠歷史股價計算市場寬度")

    total = len(per_stock)
    series = [round(sum(v[i] for v in per_stock.values()) / total * 100, 1) for i in range(BREADTH_DAYS)]
    by_sector = []
    for sec in sectors:
        vals = [per_stock[s["symbol"]][-1] for s in sec["stocks"] if s["symbol"] in per_stock]
        by_sector.append({"name": sec["name"], "above": sum(vals), "total": len(vals)})

    divergence = False
    if index_closes and len(index_closes) >= BREADTH_DAYS:
        recent = index_closes[-BREADTH_DAYS:]
        index_near_high = max(recent[-3:]) >= max(recent)
        divergence = index_near_high and series[-1] <= max(series) - 15

    pct = series[-1]
    state = "strong" if pct >= 70 else "weak" if pct <= 30 else "neutral"
    return {
        "pct": pct, "above": sum(v[-1] for v in per_stock.values()), "total": total,
        "series": series, "change20": round(series[-1] - series[0], 1),
        "state": state, "divergence": divergence, "bySector": by_sector,
    }


# ── 3. 恐慌溫度計 ───────────────────────────────────────────────────────────
FRED_HY_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"


def calc_vix_term(vix, vix3m):
    if not vix or not vix3m:
        raise RuntimeError("VIX / VIX3M 報價缺失")
    ratio = round(vix / vix3m, 3)
    state = "panic" if ratio >= 1.0 else "alert" if ratio >= 0.9 else "calm"
    return {"vix": round(vix, 2), "vix3m": round(vix3m, 2), "ratio": ratio, "state": state}


def fetch_hy_oas():
    """美國高收益債與公債的利差（%）。利差快速擴大 = 資金逃離風險資產。"""
    for attempt in range(3):  # FRED 偶爾回應很慢
        try:
            # FRED 會擋 "Mozilla/5.0" 或自訂 UA（連線直接卡住），使用 Python 預設 UA 才能正常回應
            text = http_get(FRED_HY_CSV, timeout=60, headers={}).decode("utf-8")
            break
        except Exception:
            if attempt == 2:
                raise
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) == 2 and r[0][:1].isdigit():
            try:
                rows.append((r[0], float(r[1])))
            except ValueError:
                pass  # FRED 休市日以 "." 表示
    if len(rows) < 21:
        raise RuntimeError("FRED HY OAS 資料不足")
    date, val = rows[-1]
    d5, d20 = round(val - rows[-6][1], 2), round(val - rows[-21][1], 2)
    state = "stress" if d20 >= 0.5 else "rising" if d20 >= 0.25 else "calm"
    return {"value": val, "date": date, "d5": d5, "d20": d20, "state": state,
            "series": [v for _, v in rows[-60:]]}


# ── 4. 台股月營收 ───────────────────────────────────────────────────────────
TWSE_REV_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TPEX_REV_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
MOPS_REV_URL = "https://mopsov.twse.com.tw/nas/t21/{mkt}/t21sc03_{roc}_{m}_{kind}.html"  # kind 0=本國 1=外國(KY)
_TPEX_CTX = ssl._create_unverified_context()  # TPEx 憑證鏈在部分環境驗證失敗
_MOPS_ROW = re.compile(
    r"<td align=center>(\d{4,6})</td><td align=left>[^<]*</td>((?:<td nowrap>[^<]*</td>){5})", re.I)


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _roc_to_ym(v):
    digits = re.sub(r"\D", "", str(v or ""))
    return f"{int(digits[:-2]) + 1911:04d}-{int(digits[-2:]):02d}" if len(digits) >= 5 else None


def _prev_month(ym, back):
    y, m = map(int, ym.split("-"))
    m -= back
    while m <= 0:
        m += 12; y -= 1
    return f"{y:04d}-{m:02d}"


def _mops_yoy(ym, codes):
    """從公開資訊觀測站歷史月報表抓指定月份的 YoY（%）；上市 / 上櫃 × 本國 / 外國(KY) 共四頁"""
    y, m = map(int, ym.split("-"))
    out = {}
    for mkt, kind in (("sii", 0), ("otc", 0), ("sii", 1), ("otc", 1)):
        if codes <= set(out):
            break
        try:
            html = http_get(MOPS_REV_URL.format(mkt=mkt, roc=y - 1911, m=m, kind=kind)).decode("cp950", "ignore")
        except Exception as e:
            print(f"    ⚠️ MOPS {mkt}_{kind} {ym} 失敗: {e}")
            continue
        for code, cells in _MOPS_ROW.findall(html):
            if code in codes:
                nums = re.findall(r">\s*([^<]*)</td>", cells)
                out[code] = _num(nums[4]) if len(nums) >= 5 else None
    return out


def fetch_monthly_revenue(sectors):
    """
    最新月份取自證交所 / 櫃買中心 OpenAPI，前兩個月取自公開資訊觀測站歷史報表。
    accel = YoY 連 2 個月走升（3 個點嚴格遞增）；turnedNegative = 最新 YoY < 0 且上月 ≥ 0。
    """
    names = {s["symbol"]: (s["name"], sec["name"]) for sec in sectors for s in sec["stocks"]}
    latest = {}
    for url, ctx in ((TWSE_REV_URL, None), (TPEX_REV_URL, _TPEX_CTX)):
        try:
            rows = json.loads(http_get(url, ctx=ctx))
        except Exception as e:
            print(f"    ⚠️ 月營收 OpenAPI 失敗 {url}: {e}")
            continue
        for r in rows:
            code = r.get("公司代號")
            if code in names:
                latest[code] = {"ym": _roc_to_ym(r.get("資料年月")),
                                "yoy": _num(r.get("營業收入-去年同月增減(%)")),
                                "mom": _num(r.get("營業收入-上月比較增減(%)")),
                                "rev": _num(r.get("營業收入-當月營收"))}
    if not latest:
        raise RuntimeError("證交所 / 櫃買中心月營收皆抓取失敗")

    data_month = max(v["ym"] for v in latest.values() if v["ym"])
    hist = {back: _mops_yoy(_prev_month(data_month, back), set(latest)) for back in (1, 2)}

    companies = []
    for code, (name, sector) in names.items():
        cur = latest.get(code)
        if not cur or cur["ym"] != data_month:
            continue
        ys = [cur["yoy"], hist[1].get(code), hist[2].get(code)]
        accel = None if None in ys else (ys[0] > ys[1] > ys[2])
        turned_neg = None if None in ys[:2] else (ys[0] < 0 <= ys[1])
        companies.append({"code": code, "name": name, "sector": sector,
                          "yoy": ys, "mom": cur["mom"], "rev": cur["rev"],
                          "accel": accel, "turnedNegative": turned_neg})
    return {"month": data_month,
            "months": [data_month, _prev_month(data_month, 1), _prev_month(data_month, 2)],
            "companies": companies,
            "missing": sorted(set(names) - {c["code"] for c in companies})}


# ── 5. 研究評分（概念參考 wakin61043/tw-trading-dashboard 的 lib/engine.mjs，MIT；改寫為本專案用）──
# 四個因子各自 0–100 分，缺資料（或資料過舊）的因子直接排除、剩下的權重重新標準化，
# 並揭露「有效權重」，避免拿不完整的分數跟完整分數直接比。分數是研究排序用，不是買賣訊號。
SCORE_WEIGHTS = {"technical": 30, "chips": 30, "industry": 25, "revenue": 15}
SCORE_LABELS = {"technical": "技術", "chips": "法人", "industry": "族群", "revenue": "營收"}
INST_CACHE_DAYS = 30
T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86?date={d}&selectType=ALLBUT0999&response=json"
TPEX_INST_URL = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={d}&response=json"


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def _days_between(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _inst_rows(fields, rows, code_keys, net_keys):
    """從表頭找出「代號」與「三大法人買賣超合計」兩欄；找不到合計欄就回傳空 dict。
    直接取官方合計欄，不自己加總外資／投信／自營商，避免自營商（自行買賣＋避險）重複計算。"""
    fields = [str(f).replace(" ", "") for f in fields]
    ci = next((i for i, f in enumerate(fields) if any(k in f for k in code_keys)), None)
    ni = next((i for i, f in enumerate(fields) if any(k in f for k in net_keys)), None)
    if ci is None or ni is None:
        return {}
    out = {}
    for r in rows:
        v = _num(str(r[ni]).replace(",", ""))
        if v is not None:
            out[str(r[ci]).strip()] = v
    return out


def _fetch_inst_day(date):
    """單日三大法人買賣超（股數）：上市 T86 + 上櫃 TPEx；任一邊失敗只少那一邊。"""
    import time
    d = date.replace("-", "")
    day = {}
    try:
        j = json.loads(http_get(T86_URL.format(d=d)))
        if j.get("stat") == "OK":
            day.update(_inst_rows(j.get("fields", []), j.get("data", []), ["證券代號"], ["三大法人買賣超股數"]))
    except Exception as e:
        print(f"    ⚠️ T86 {date} 失敗: {e}")
    time.sleep(2.5)  # 證交所對連續請求會封鎖 IP
    try:
        j = json.loads(http_get(TPEX_INST_URL.format(d=date.replace("-", "/")), ctx=_TPEX_CTX))
        for t in j.get("tables", []):
            day.update(_inst_rows(t.get("fields", []), t.get("data", []), ["代號"], ["三大法人買賣超股數合計", "三大法人買賣超股數"]))
    except Exception as e:
        print(f"    ⚠️ 櫃買法人 {date} 失敗: {e}")
    time.sleep(1.5)
    return day


def update_inst_history(trade_dates, codes, cache_path="inst_history.json"):
    """維護近 INST_CACHE_DAYS 個交易日的法人買賣超快取（只存研究名單內的代號）。
    每天只補抓快取裡沒有的日期，第一次執行約需 1–2 分鐘。回傳 {date: {code: 淨股數}}。"""
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    want = trade_dates[-INST_CACHE_DAYS:]
    codes = set(codes)
    for date in want:
        if date in cache and cache[date]:
            continue
        day = _fetch_inst_day(date)
        if day:
            cache[date] = {c: v for c, v in day.items() if c in codes}
            print(f"    法人 {date}：{len(cache[date])} 檔")
    cache = {d: cache[d] for d in sorted(cache) if d in want}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
    return cache


def _missing(reason):
    return {"score": None, "reasons": [reason]}


def score_technical(bars, cutoff):
    if len(bars) < 80:
        return _missing(f"K 線不足 80 日（目前 {len(bars)} 日）")
    if _days_between(bars[-1]["date"], cutoff) > 7:
        return _missing(f"行情日期過舊：{bars[-1]['date']}")
    c = [b["close"] for b in bars]
    ma = lambda n, off=0: sum(c[len(c) - n - off: len(c) - off]) / n
    last, m20, m60 = c[-1], ma(20), ma(60)
    m120 = ma(120) if len(c) >= 120 else None
    r20 = (last / c[-21] - 1) * 100
    r60 = (last / c[-61] - 1) * 100
    slope = (m60 / ma(60, 20) - 1) * 100
    drawdown = (last / max(c[-60:]) - 1) * 100
    deviation = (last / m20 - 1) * 100
    checks = [last > m20, m20 > m60] + ([m60 > m120] if m120 else [])
    trend = sum(checks) / len(checks) * 100
    momentum = _clamp(50 + r60 * 2)
    stability = _clamp(100 + drawdown * 4 - max(0, deviation - 15) * 3)
    score = round(trend * .4 + momentum * .25 + _clamp(50 + slope * 5) * .2 + stability * .15)
    reasons = [
        f"均線：收盤{'高於' if last > m20 else '低於'}月線、月線{'高於' if m20 > m60 else '低於'}季線"
        + ("" if m120 else "（K 線未滿 120 日，不看半年線）"),
        f"近 60 日 {r60:+.1f}%；季線 20 日變化 {slope:+.1f}%",
        f"距 60 日高點 {drawdown:.1f}%；月線乖離 {deviation:+.1f}%",
    ]
    return {"score": score, "r20": round(r20, 1), "r60": round(r60, 1), "deviation": round(deviation, 1),
            "above60": last > m60, "date": bars[-1]["date"], "reasons": reasons}


def score_chips(code, bars, inst):
    dates = [b["date"] for b in bars[-20:]]
    if len(dates) < 20:
        return _missing("行情不足 20 日，無法標準化法人買賣超")
    have = [d for d in dates if d in inst and code in inst[d]]
    if len(have) < 18:
        return _missing(f"近 20 個交易日法人資料只有 {len(have)} 日（需 ≥18）")
    if _days_between(have[-1], dates[-1]) > 5:
        return _missing(f"法人資料落後行情：{have[-1]}")
    vol = sum(b["volume"] for b in bars[-20:])
    if vol <= 0:
        return _missing("無有效成交量")
    nets = [inst[d][code] for d in have]
    net20, ratio = sum(nets), sum(nets) / vol * 100
    positive = sum(1 for n in nets if n > 0) / len(nets)
    score = round(_clamp(50 + ratio * 5) * .6 + positive * 100 * .4)
    net5 = sum(nets[-5:])
    return {"score": score, "net20": round(net20 / 1000), "net5": round(net5 / 1000), "ratio": round(ratio, 2),
            "reasons": [f"近 20 日法人 {net20 / 1000:+,.0f} 張，占成交量 {ratio:+.2f}%",
                        f"買超天數 {positive * 100:.0f}%；近 5 日 {net5 / 1000:+,.0f} 張"]}


def score_revenue(rev, cutoff):
    if not rev or rev.get("yoy") is None:
        return _missing("尚無月營收年增率")
    if _days_between(rev["ym"] + "-01", cutoff) > 75:
        return _missing(f"月營收過舊：{rev['ym']}")
    y = rev["yoy"]
    score = round(_clamp(50 + y + (10 if rev.get("accel") else 0) - (10 if rev.get("turnedNegative") else 0)))
    tag = "；年增連 2 月加速 +10" if rev.get("accel") else "；年增由正轉負 −10" if rev.get("turnedNegative") else ""
    return {"score": score, "yoy": round(y, 1), "reasons": [f"{rev['ym']} 營收年增 {y:+.1f}%{tag}"]}


def calc_research_scores(sectors, bars_by_code, inst, monthly_revenue, cutoff):
    """sectors：[{name, stocks:[{symbol,name}]}]；bars_by_code：{代號: OHLCV}；inst：update_inst_history() 的結果。"""
    mr = {c["code"]: {"ym": (monthly_revenue or {}).get("month"), "yoy": c["yoy"][0],
                      "accel": c.get("accel"), "turnedNegative": c.get("turnedNegative")}
          for c in (monthly_revenue or {}).get("companies", [])}
    stocks = []
    for sec in sectors:
        for s in sec["stocks"]:
            code, bars = s["symbol"].split(".")[0], bars_by_code.get(s["symbol"].split(".")[0], [])
            stale = not bars or _days_between(bars[-1]["date"], cutoff) > 7
            stocks.append({"code": code, "name": s["name"], "sector": sec["name"], "stale": stale,
                           "price": round(bars[-1]["close"], 2) if bars else None,
                           "technical": score_technical(bars, cutoff) if bars else _missing("沒有行情資料"),
                           "chips": score_chips(code, bars, inst) if bars else _missing("沒有行情資料"),
                           "revenue": score_revenue(mr.get(code), cutoff)})

    # 族群：站上季線比例 40% ＋ 營收年增中位數 40% ＋ 60 日報酬中位數 20%；有效樣本需 ≥5 檔且 ≥50%
    sector_scores = []
    for sec in sectors:
        members = [s for s in stocks if s["sector"] == sec["name"]]
        ok = [s for s in members if not s["stale"] and s["technical"]["score"] is not None and s["revenue"]["score"] is not None]
        valid = len(ok) >= min(5, len(members)) and len(ok) >= len(members) * .5
        if valid:
            breadth = sum(1 for s in ok if s["technical"]["above60"]) / len(ok) * 100
            growth = _median([s["revenue"]["yoy"] for s in ok])
            mom = _median([s["technical"]["r60"] for s in ok])
            score = round(breadth * .4 + _clamp(50 + growth) * .4 + _clamp(50 + mom * 2) * .2)
            ind = {"score": score, "reasons": [f"{sec['name']}：站上季線 {breadth:.0f}%、營收年增中位數 {growth:+.1f}%、60 日報酬中位數 {mom:+.1f}%（{len(ok)}/{len(members)} 檔有效）"]}
        else:
            score, ind = None, _missing(f"{sec['name']} 有效樣本 {len(ok)}/{len(members)} 檔，未達門檻")
        sector_scores.append({"name": sec["name"], "score": score, "covered": len(ok), "count": len(members)})
        for s in members:
            s["industry"] = ind

    total_w = sum(SCORE_WEIGHTS.values())
    for s in stocks:
        avail = [k for k in SCORE_WEIGHTS if s[k]["score"] is not None]
        w = sum(SCORE_WEIGHTS[k] for k in avail)
        s["coverage"] = round(w / total_w * 100)
        s["complete"] = len(avail) == len(SCORE_WEIGHTS)
        s["score"] = round(sum(s[k]["score"] * SCORE_WEIGHTS[k] for k in avail) / w) if w and not s["stale"] else None
        sc = s["score"]
        s["rating"] = "待更新" if sc is None else ("" if s["complete"] else "暫評・") + (
            "強勢" if sc >= 75 else "中性偏強" if sc >= 55 else "中性偏弱" if sc >= 40 else "弱勢")
        risks = []
        if not s["complete"]:
            risks.append(f"有效權重 {s['coverage']}%，缺漏因子已排除並重新加權，不宜與完整評分直接比較")
        if s["stale"]:
            risks.append("行情超過 7 天或未取得，暫停評分")
        if (s["technical"].get("deviation") or 0) > 15:
            risks.append("距月線超過 15%，留意回檔")
        if (s["chips"].get("net20") or 0) < 0:
            risks.append("法人近 20 日累計賣超")
        s["risks"] = risks
        for k in SCORE_WEIGHTS:  # 前端不需要的中間值不輸出，data.json 保持精簡
            s[k] = {"score": s[k]["score"], "reasons": s[k]["reasons"]}
    # 完整評分排前面、暫評排後面，避免缺因子的高分擠到最上方
    stocks.sort(key=lambda s: (s["score"] is None, not s["complete"], -(s["score"] or 0)))
    return {"date": cutoff, "weights": SCORE_WEIGHTS, "labels": SCORE_LABELS,
            "sectors": sector_scores, "stocks": stocks}
