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
