<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0C447C">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="市場早報">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="icons/icon-192.png">
<title>市場早報</title>
<style>
:root{
  --bg:#f5f5f0;--card:#fff;--bdr:rgba(0,0,0,.08);
  --tx:#18180e;--mu:#6b6b60;--hi:#9b9b8e;
  --G:#3B6D11;--Gbg:#EAF3DE;--Gm:#639922;
  --R:#A32D2D;--Rbg:#FCEBEB;--Rm:#E24B4A;
  --B:#0C447C;--Bbg:#E6F1FB;--Bm:#378ADD;
  --r:14px;--rs:10px;
}
@media(prefers-color-scheme:dark){
  :root{--bg:#141410;--card:#1e1e1a;--bdr:rgba(255,255,255,.08);--tx:#eeeee4;--mu:#909088;--hi:#5a5a52;--G:#C0DD97;--Gbg:#1a3306;--Gm:#97C459;--R:#F7C1C1;--Rbg:#3d1010;--Rm:#E24B4A;--B:#B5D4F4;--Bbg:#0a1e38;--Bm:#378ADD;}
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden}
body{font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',sans-serif;background:var(--bg);color:var(--tx);display:flex;flex-direction:column}
.topbar{background:var(--B);color:#fff;padding:calc(env(safe-area-inset-top,0px) + 12px) 16px 12px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between}
.topbar h1{font-size:17px;font-weight:700}
.topbar p{font-size:11px;opacity:.7;margin-top:1px}
.scroll{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:12px 12px calc(env(safe-area-inset-bottom,0px)+20px)}

/* signal banner */
.signal{border-radius:var(--r);padding:14px 16px;margin-bottom:12px;display:flex;align-items:center;gap:12px;border:1px solid transparent}
.signal.up{background:var(--Gbg);border-color:var(--Gm)}
.signal.dn{background:var(--Rbg);border-color:var(--Rm)}
.signal.fl{background:var(--card);border-color:var(--bdr)}
.sig-ic{font-size:26px;flex-shrink:0}
.sig-bd{flex:1;min-width:0}
.sig-t{font-size:13px;font-weight:700}
.sig-t.up{color:var(--G)}.sig-t.dn{color:var(--R)}.sig-t.fl{color:var(--tx)}
.sig-d{font-size:12px;margin-top:2px;line-height:1.4}
.sig-d.up{color:var(--Gm)}.sig-d.dn{color:var(--Rm)}.sig-d.fl{color:var(--mu)}
.sig-a{font-size:10px;color:var(--hi);margin-top:3px}
.sig-v{flex-shrink:0;text-align:right}
.sig-v .big{font-size:20px;font-weight:800}
.sig-v .big.up{color:var(--G)}.sig-v .big.dn{color:var(--R)}.sig-v .big.fl{color:var(--tx)}
.sig-v .sm{font-size:10px;color:var(--hi);margin-top:2px}

/* index grid */
.ig{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.ic{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:12px 14px}
.ic.hl{border-color:var(--Gm);border-width:2px}
.ic-l{font-size:11px;color:var(--mu);margin-bottom:2px;display:flex;align-items:center;gap:4px}
.lead-tag{font-size:9px;background:var(--Gbg);color:var(--G);padding:1px 5px;border-radius:4px;font-weight:700}
.ic-v{font-size:20px;font-weight:800;letter-spacing:-.02em}
.badge{display:inline-flex;align-items:center;font-size:11px;padding:3px 8px;border-radius:6px;margin-top:5px;font-weight:600}
.badge.up{background:var(--Gbg);color:var(--G)}
.badge.dn{background:var(--Rbg);color:var(--R)}
.badge.fl{background:var(--bg);color:var(--mu)}
.ic-p{font-size:10px;color:var(--hi);margin-top:3px}

/* heatmap */
.card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:14px;margin-bottom:12px}
.c-title{font-size:13px;font-weight:700;margin-bottom:2px}
.c-sub{font-size:11px;color:var(--mu);margin-bottom:10px;line-height:1.45}
.seg{display:flex;border:1px solid var(--bdr);border-radius:var(--rs);overflow:hidden;margin-bottom:10px}
.sb{flex:1;font-size:12px;padding:9px 4px;text-align:center;background:transparent;border:none;color:var(--mu);cursor:pointer;font-family:inherit;font-weight:500;border-right:1px solid var(--bdr)}
.sb:last-child{border-right:none}
.sb.a{background:var(--Bbg);color:var(--B);font-weight:700}
.hr{display:flex;align-items:center;gap:5px;margin-bottom:4px}
.hn{font-size:10px;color:var(--mu);width:44px;flex-shrink:0;text-align:right}
.hc-wrap{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;flex:1}
.hcell{border-radius:4px;padding:5px 2px;text-align:center;font-size:9px;font-weight:700;line-height:1.3}

.status{display:flex;align-items:center;gap:6px;margin-bottom:10px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--Gm);flex-shrink:0}
.dot.busy{background:#BA7517}
.dot.err{background:var(--Rm)}
.stxt{font-size:11px;color:var(--hi);flex:1}
.lupd{font-size:10px;color:var(--hi);text-align:center;padding-bottom:4px}

.skeleton{background:var(--bdr);border-radius:4px;animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.4}50%{opacity:.9}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <h1>市場早報</h1>
    <p id="topSub">每日 08:00 自動更新</p>
  </div>
  <button onclick="loadData()" style="font-size:12px;padding:6px 12px;border-radius:20px;border:1.5px solid rgba(255,255,255,.5);background:transparent;color:#fff;cursor:pointer;font-family:inherit">↻ 更新</button>
</div>

<div class="scroll">
  <div class="status">
    <span class="dot" id="dot"></span>
    <span class="stxt" id="stxt">載入中...</span>
  </div>
  <div id="banner"></div>
  <div class="ig" id="idxGrid">
    <div class="ic skeleton" style="height:90px"></div>
    <div class="ic skeleton" style="height:90px"></div>
    <div class="ic skeleton" style="height:90px"></div>
    <div class="ic skeleton" style="height:90px"></div>
  </div>
  <div class="card">
    <div class="c-title">板塊熱力圖</div>
    <div class="c-sub">深綠強漲 · 深紅重跌（富邦即時資料）</div>
    <div class="seg" id="seg"></div>
    <div id="hg"></div>
  </div>
  <div class="lupd" id="lupd"></div>
</div>

<script>
// 這個網址由 GitHub Pages 自動提供，與 index.html 同目錄
const DATA_URL = './data.json';

let data = null;
let tab = 0;  // 板塊 index

const s = v => v >= 0 ? '+' : '';
const f = (v, d=2) => (+v||0).toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});
function hc(v){
  if(v>2)    return{bg:'#3B6D11',fg:'#C0DD97'};
  if(v>0.8)  return{bg:'#639922',fg:'#EAF3DE'};
  if(v>0.2)  return{bg:'#97C459',fg:'#27500A'};
  if(v>-0.2) return{bg:'#888780',fg:'#F1EFE8'};
  if(v>-0.8) return{bg:'#E24B4A',fg:'#FCEBEB'};
  if(v>-2)   return{bg:'#A32D2D',fg:'#F7C1C1'};
  return      {bg:'#501313',fg:'#F0ABAB'};
}

function renderBanner(){
  const tsm = data.indices.TSM;
  if(!tsm) return;
  const c = tsm.changePercent;
  const dir = c > 0.3 ? 'up' : c < -0.3 ? 'dn' : 'fl';
  const strength = Math.abs(c) > 2 ? '強烈' : Math.abs(c) > 1 ? '明顯' : '溫和';
  const ico = dir==='up' ? '📈' : dir==='dn' ? '📉' : '📊';
  const sig = dir==='up' ? `${strength}看多訊號 — 台股半導體預期開高`
            : dir==='dn' ? `${strength}看空訊號 — 台股半導體預期開低`
            : '訊號偏中性 — 方向待觀察';
  document.getElementById('banner').innerHTML = `
    <div class="signal ${dir}">
      <div class="sig-ic">${ico}</div>
      <div class="sig-bd">
        <div class="sig-t ${dir}">台積電 ADR 領先訊號</div>
        <div class="sig-d ${dir}">${sig}</div>
        <div class="sig-a">昨收 $${f(tsm.price)} · 來源：富邦即時資料</div>
      </div>
      <div class="sig-v">
        <div class="big ${dir}">${s(c)}${c.toFixed(2)}%</div>
        <div class="sm">前 $${f(tsm.prev)}</div>
      </div>
    </div>`;
}

function renderIdx(){
  const entries = [
    {key:'TSM',  label:'台積電',      lead:true,  dollar:true},
    {key:'TWII', label:'台股 TAIEX',  lead:false, dollar:false},
  ];
  document.getElementById('idxGrid').innerHTML = entries.map(e => {
    const d = data.indices[e.key];
    if(!d) return '';
    const c = d.changePercent;
    const dir = c > 0 ? 'up' : c < 0 ? 'dn' : 'fl';
    return `<div class="ic${e.lead?' hl':''}">
      <div class="ic-l">${e.label}${e.lead?'<span class="lead-tag">領先</span>':''}</div>
      <div class="ic-v">${e.dollar?'$':''}${f(d.price, e.dollar?2:1)}</div>
      <div class="badge ${dir}">${c>=0?'▲':'▼'} ${Math.abs(c).toFixed(2)}%</div>
      <div class="ic-p">前 ${e.dollar?'$':''}${f(d.prev, e.dollar?2:1)}</div>
    </div>`;
  }).join('');
}

function renderHeat(){
  const sectors = data.sectors;
  document.getElementById('seg').innerHTML = sectors.map((sec, i) =>
    `<button class="sb${tab===i?' a':''}" onclick="setTab(${i})">${sec.name}</button>`
  ).join('');
  const sec = sectors[tab];
  document.getElementById('hg').innerHTML = sec ? `
    <div class="hr">
      <div class="hn">${sec.name}</div>
      <div class="hc-wrap">
        ${sec.stocks.map(st => {
          const col = hc(st.changePercent);
          return `<div class="hcell" style="background:${col.bg};color:${col.fg}"
            title="${st.name} ${s(st.changePercent)}${st.changePercent.toFixed(2)}%">
            ${st.name.substring(0,3)}<br>${s(st.changePercent)}${st.changePercent.toFixed(1)}%
          </div>`;
        }).join('')}
      </div>
    </div>` : '';
}

function setTab(i){ tab = i; renderHeat(); }

function renderAll(){
  renderBanner();
  renderIdx();
  renderHeat();
  const upd = new Date(data.updated);
  document.getElementById('lupd').textContent = `資料時間：${upd.toLocaleString('zh-TW')}（${data.source === 'fubon_neo' ? '富邦即時' : '占位資料'}）`;
  document.getElementById('topSub').textContent = `${data.date} 更新`;
}

async function loadData(){
  const dot = document.getElementById('dot');
  const stxt = document.getElementById('stxt');
  dot.className = 'dot busy';
  stxt.textContent = '抓取資料中...';
  try {
    // 加上時間戳避免快取
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`);
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
    dot.className = 'dot';
    stxt.textContent = data.source === 'fubon_neo' ? '富邦即時資料' : '占位資料';
    renderAll();
  } catch(e) {
    dot.className = 'dot err';
    stxt.textContent = `載入失敗：${e.message}`;
  }
}

loadData();
</script>
</body>
</html>
