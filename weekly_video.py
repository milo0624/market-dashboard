#!/usr/bin/env python3
"""
夜盤紙上交易週報影片：讀 public/night_signal.json、public/night_history.json，
產生一支 30 秒直式影片（1080×1920）的 HyperFrames 作品 → video/index.html，
再由 GitHub Actions「夜盤週報影片」用 `npx hyperframes render video` 輸出 MP4、推播到 Telegram。

段落（秒）：0–3.5 標題｜3.5–11 日K＋60MA｜11–20 本週每筆交易｜20–27 累計 vs 回測｜27–30 結尾
規則：資料全部寫死在 HTML 裡（不連網、不用亂數、不用現在時間），符合 HyperFrames 可重現渲染的要求。
用法：python3 weekly_video.py [YYYY-MM-DD]   ← 週報結束日，省略則用最新判斷日
"""
import html, json, os, shutil, sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "video")
W, H = 1080, 1920
UP, DN, MA = "#38a169", "#e53e3e", "#63b3ed"     # 與儀表板一致：綠漲紅跌、藍色均線


def fmt(v, sign=True):
    if v is None:
        return "—"
    s = f"{abs(round(v)):,}"
    return (("+" if v >= 0 else "−") if sign else ("" if v >= 0 else "−")) + s


def kline_svg(bars, w=960, h=900):
    lo = min(min(b["l"] for b in bars), min(b["ma"] for b in bars if b.get("ma")))
    hi = max(max(b["h"] for b in bars), max(b["ma"] for b in bars if b.get("ma")))
    pad = (hi - lo) * 0.06; lo -= pad; hi += pad
    slot = w / len(bars); bw = max(4, slot * 0.6)
    y = lambda v: 40 + (hi - v) / (hi - lo) * h   # 上下各留 40 讓刻度文字不被切掉
    parts = []
    for g in range(4):
        v = lo + (hi - lo) * g / 3; yy = y(v)
        parts.append(f'<line x1="0" y1="{yy:.1f}" x2="{w}" y2="{yy:.1f}" stroke="#2d3748" stroke-width="2"/>'
                     f'<text x="{w + 12}" y="{yy + 10:.1f}" fill="#718096" font-size="30">{round(v):,}</text>')
    for i, b in enumerate(bars):
        cx = i * slot + slot / 2; col = UP if b["c"] >= b["o"] else DN
        top, bot = y(max(b["o"], b["c"])), y(min(b["o"], b["c"]))
        parts.append(f'<line x1="{cx:.1f}" y1="{y(b["h"]):.1f}" x2="{cx:.1f}" y2="{y(b["l"]):.1f}" stroke="{col}" stroke-width="3"/>'
                     f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(3, bot - top):.1f}" fill="{col}"/>')
    pts = " ".join(f"{i * slot + slot / 2:.1f},{y(b['ma']):.1f}" for i, b in enumerate(bars) if b.get("ma"))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{MA}" stroke-width="6" stroke-linejoin="round"/>')
    last = bars[-1]
    parts.append(f'<circle cx="{(len(bars) - 0.5) * slot:.1f}" cy="{y(last["c"]):.1f}" r="12" fill="#fff"/>')
    return f'<svg viewBox="0 0 {w + 150} {h + 80}" style="width:100%;height:auto;display:block">{"".join(parts)}</svg>'


def build(end=None):
    sig = json.load(open(os.path.join(HERE, "public/night_signal.json"), encoding="utf-8"))
    hist = json.load(open(os.path.join(HERE, "public/night_history.json"), encoding="utf-8"))
    end = date.fromisoformat(end) if end else date.fromisoformat(sig["date"])
    start = end - timedelta(days=6)
    week = [h for h in hist if "result" in h and start <= date.fromisoformat(h["date"]) <= end]
    bars = sig.get("bars") or []
    p, bt = sig.get("paper", {}), sig.get("backtest", {})
    week_total = sum(h["result"]["pnl"] for h in week)

    # ── 段落 3：本週每筆交易 ──
    rows = []
    for i, h in enumerate(week[-5:]):
        r = h["result"]; win = r["pnl"] > 0
        d = date.fromisoformat(h["date"])
        rows.append(f'''<div class="trade" id="tr{i}">
          <div class="tr-date">{d.month}/{d.day} {"一二三四五六日"[d.weekday()]}晚</div>
          <div class="tr-mid">{round(r["entry"]):,} → {round(r["exit"]):,}<span class="tr-how">{html.escape(r["how"])}</span></div>
          <div class="tr-pnl" style="color:{UP if win else DN}">{fmt(r["pnl"])}</div></div>''')
    if not rows:
        rows.append('<div class="trade" id="tr0"><div class="tr-mid">本週沒有交易（均線之下或休市）</div></div>')

    # ── 段落 4：累計判讀 ──
    n = p.get("trades") or 0
    lo_b, hi_b = (p.get("expTotal", 0) - (p.get("band") or 0)), (p.get("expTotal", 0) + (p.get("band") or 0))
    if n < 20:
        verdict, vcol = "樣本還少（< 20 筆），先不下結論", "#a0aec0"
    elif p.get("total", 0) < lo_b:
        verdict, vcol = "⚠️ 低於回測正常範圍，暫停檢查", DN
    else:
        verdict, vcol = "在回測預期的正常範圍內", UP
    last = bars[-1] if bars else None
    trend = ("多頭" if last and last.get("ma") and last["c"] > last["ma"] else "空頭") if last else "—"
    gap = (last["c"] / last["ma"] - 1) * 100 if last and last.get("ma") else 0

    data_rows = [("勝率", f'{p.get("winRate") or 0:.0f}%', f'{bt.get("winRate", 0):.0f}%'),
                 ("平均每筆", fmt(p.get("avg")), fmt(bt.get("avg"))),
                 ("停損比例", f'{p.get("stopRate") or 0:.0f}%', f'{bt.get("stopRate", 0):.0f}%')]
    cmp_html = "".join(f'<div class="cmp-row" id="cr{i}"><span class="cmp-k">{k}</span><span class="cmp-v">{a}</span>'
                       f'<span class="cmp-b">回測 {b}</span></div>' for i, (k, a, b) in enumerate(data_rows))
    n_rows = len(rows)

    page = f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<script src="gsap.min.js"></script>
<style>
  @font-face {{ font-family: "Noto Sans CJK TC"; src: local("Noto Sans CJK TC"); font-weight: 400; }}
  @font-face {{ font-family: "Noto Sans CJK TC"; src: local("Noto Sans CJK TC Black"), local("Noto Sans CJK TC"); font-weight: 900; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#0f141c; }}
  #root {{ position:relative; width:100%; height:100%; color:#f7fafc;
          font-family:"Noto Sans CJK TC",sans-serif; }}
  .clip {{ position:absolute; inset:0; padding:150px 70px; display:flex; flex-direction:column; justify-content:center; }}
  .eyebrow {{ font-size:40px; color:#a0aec0; letter-spacing:.08em; }}
  .h1 {{ font-size:104px; font-weight:900; line-height:1.15; margin-top:30px; }}
  .sub {{ font-size:44px; color:#cbd5e0; margin-top:40px; line-height:1.5; }}
  .badge {{ display:inline-block; font-size:46px; font-weight:800; padding:14px 34px; border-radius:60px; margin-top:50px; }}
  .h2 {{ font-size:72px; font-weight:900; margin-bottom:50px; }}
  .chart {{ margin-top:20px; }}
  .legend {{ font-size:36px; color:#a0aec0; margin-top:30px; }}
  .trade {{ display:flex; align-items:center; background:#1a2230; border-radius:28px; padding:34px 40px; margin-bottom:28px; }}
  .tr-date {{ font-size:42px; width:250px; color:#cbd5e0; }}
  .tr-mid {{ flex:1; font-size:40px; }}
  .tr-how {{ display:block; font-size:32px; color:#718096; margin-top:6px; }}
  .tr-pnl {{ font-size:54px; font-weight:900; }}
  .wk-total {{ font-size:48px; margin-top:20px; color:#cbd5e0; }}
  .big {{ font-size:150px; font-weight:900; line-height:1; margin:10px 0 50px; }}
  .cmp-row {{ display:flex; align-items:baseline; border-bottom:2px solid #2d3748; padding:30px 0; }}
  .cmp-k {{ font-size:44px; color:#a0aec0; width:300px; }}
  .cmp-v {{ font-size:64px; font-weight:900; flex:1; }}
  .cmp-b {{ font-size:38px; color:#718096; }}
  .verdict {{ font-size:46px; font-weight:800; margin-top:50px; line-height:1.5; }}
  .center {{ justify-content:center; align-items:center; text-align:center; }}
</style></head>
<body>
<div id="root" data-composition-id="weekly" data-start="0" data-duration="30" data-width="{W}" data-height="{H}">

  <section id="s1" class="clip center" data-start="0" data-duration="3.5" data-track-index="0">
    <div class="eyebrow" id="s1a">夜盤紙上交易 · 週報</div>
    <div class="h1" id="s1b">{start.month}/{start.day} – {end.month}/{end.day}</div>
    <div class="sub" id="s1c">只抱夜盤 ＋ 60 日均線過濾<br>＋ 300 點停損 ＋ 連假不留倉</div>
  </section>

  <section id="s2" class="clip" data-start="3.5" data-duration="7.5" data-track-index="0">
    <div class="h2" id="s2a">台指期日K · 近 {len(bars)} 天</div>
    <div class="chart" id="s2chart">{kline_svg(bars) if bars else ""}</div>
    <div class="legend">K 棒：日盤（綠漲紅跌）　藍線：60 日均線</div>
    <div class="badge" id="s2b" style="background:{UP if trend == "多頭" else DN}22;color:{UP if trend == "多頭" else DN}">
      {trend}：收盤 {round(last["c"]) if last else 0:,}，距均線 {gap:+.2f}%</div>
  </section>

  <section id="s3" class="clip" data-start="11" data-duration="9" data-track-index="0">
    <div class="h2">本週每筆紙上交易</div>
    {"".join(rows)}
    <div class="wk-total" id="s3t">本週合計 <b style="color:{UP if week_total >= 0 else DN}">{fmt(week_total)} 元</b>（{len(week)} 筆，1 口微台）</div>
  </section>

  <section id="s4" class="clip" data-start="20" data-duration="7" data-track-index="0">
    <div class="eyebrow">累計 {n} 筆（自 {p.get("since") or "—"}）</div>
    <div class="big" id="s4big" style="color:{UP if (p.get("total") or 0) >= 0 else DN}">{fmt(p.get("total"))}</div>
    {cmp_html}
    <div class="verdict" id="s4v" style="color:{vcol}">{verdict}<br>
      <span style="font-size:36px;color:#718096;font-weight:400">回測預期 {fmt(p.get("expTotal"))}，正常範圍 {fmt(lo_b)} ～ {fmt(hi_b)}</span></div>
  </section>

  <section id="s5" class="clip center" data-start="27" data-duration="3" data-track-index="0">
    <div class="h1" id="s5a" style="font-size:84px">下週一 13:55<br>繼續判斷</div>
    <div class="sub" id="s5b">紙上交易紀錄，不構成投資建議</div>
  </section>
</div>
<script>
  window.__timelines = window.__timelines || {{}};
  const tl = gsap.timeline({{ paused: true }});
  tl.from("#s1a", {{ opacity: 0, y: 30, duration: 0.5 }}, 0.2)
    .from("#s1b", {{ opacity: 0, y: 40, duration: 0.6, ease: "power3.out" }}, 0.4)
    .from("#s1c", {{ opacity: 0, duration: 0.6 }}, 1.0)
    .from("#s2a", {{ opacity: 0, y: 30, duration: 0.5 }}, 3.6)
    .fromTo("#s2chart", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: 3.2, ease: "power1.inOut" }}, 3.8)
    .from("#s2b", {{ opacity: 0, scale: 0.9, duration: 0.5 }}, 7.2);
  for (let i = 0; i < {n_rows}; i++) {{
    tl.from("#tr" + i, {{ opacity: 0, x: 80, duration: 0.45, ease: "power2.out" }}, 11.4 + i * 0.9);
  }}
  tl.from("#s3t", {{ opacity: 0, duration: 0.5 }}, 11.6 + {n_rows} * 0.9)
    .from("#s4big", {{ opacity: 0, scale: 0.85, duration: 0.6, ease: "back.out(1.6)" }}, 20.3);
  for (let i = 0; i < 3; i++) {{
    tl.from("#cr" + i, {{ opacity: 0, y: 30, duration: 0.4 }}, 21.2 + i * 0.6);
  }}
  tl.from("#s4v", {{ opacity: 0, duration: 0.6 }}, 23.4)
    .from("#s5a", {{ opacity: 0, y: 40, duration: 0.6 }}, 27.2)
    .from("#s5b", {{ opacity: 0, duration: 0.5 }}, 27.8);
  window.__timelines["weekly"] = tl;
  tl.seek(0);
</script>
</body></html>'''
    os.makedirs(OUT_DIR, exist_ok=True)
    open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(page)
    caption = (f"🌙 夜盤紙上交易週報 {start.month}/{start.day}–{end.month}/{end.day}\n"
               f"本週 {len(week)} 筆，合計 {fmt(week_total)} 元；累計 {n} 筆 {fmt(p.get('total'))} 元\n"
               f"目前{trend}（距 60 日均線 {gap:+.2f}%）")
    open(os.path.join(OUT_DIR, "caption.txt"), "w", encoding="utf-8").write(caption)
    print(caption)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
