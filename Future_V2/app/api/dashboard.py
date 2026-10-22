"""Read-only operator dashboard rendered as a single self-contained page."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Agent Desk</title>
<style>
:root{--bg:#eef3e8;--panel:#fffaf0;--panel2:#f7f0df;--ink:#10251f;--muted:#6a7871;--line:#17382e;--good:#cfe8cf;--bad:#f7d5c8;--warn:#ffe0b8;--accent:#ef7545;--shadow:0 10px 30px #17382e18}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#d7ebd5,#f4f0e5 48%,#cddfd4);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;font-size:14px}main{max-width:1480px;margin:0 auto;padding:24px}.mono{font-family:"DM Mono",ui-monospace,SFMono-Regular,Menlo,monospace}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}.title{font-size:clamp(30px,4vw,52px);line-height:.95;letter-spacing:-.06em;font-weight:900;margin:0}.toolbar{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.pill,button,select{border:1.5px solid var(--line);border-radius:999px;background:#fffaf0cc;padding:8px 12px;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink)}.pill.ok{background:var(--good)}.pill.bad{background:var(--bad)}button{cursor:pointer}button:hover{background:#fff}button:disabled{opacity:.6;cursor:progress}.layout{display:grid;grid-template-columns:1.15fr .85fr;gap:16px}.card{border:2px solid var(--line);background:#fffaf0d9;box-shadow:var(--shadow);padding:16px;border-radius:16px;min-width:0}.card h2{margin:0 0 12px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}.stack{display:grid;gap:16px}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.kpi{border:1.5px solid #17382e55;background:var(--panel2);border-radius:14px;padding:13px}.kpi .k{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}.kpi .v{font-size:25px;font-weight:850;margin:5px 0 2px;letter-spacing:-.04em}.kpi .s{font-size:12px;color:var(--muted);line-height:1.35}.hero{display:grid;grid-template-columns:220px 1fr;gap:14px;align-items:stretch}.verdict{border-radius:16px;border:2px solid var(--line);display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:18px;background:var(--panel2)}.verdict .action{font-size:42px;font-weight:900;letter-spacing:-.06em;text-transform:uppercase}.verdict.buy{background:var(--good)}.verdict.sell,.verdict.bad{background:var(--bad)}.verdict.hold{background:#eee8d9}.facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.fact{border:1px solid #17382e33;border-radius:12px;padding:10px;background:#ffffff73}.fact b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700}.fact span{display:block;margin-top:4px;font-weight:750}.agent-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.agent{border:1.5px solid #17382e55;border-radius:14px;background:#fffdf7;padding:11px}.agent .name{display:flex;justify-content:space-between;gap:8px;font-weight:850}.agent .meta{font-size:12px;color:var(--muted);margin-top:6px;line-height:1.45}.agent.veto{outline:3px solid #b23a2b33}.tag{display:inline-flex;align-items:center;border-radius:999px;border:1px solid var(--line);padding:2px 8px;font-size:11px;text-transform:uppercase;font-weight:800}.tag.buy{background:var(--good)}.tag.sell{background:var(--bad)}.tag.hold{background:#e8e2d3}.tag.bad{background:var(--bad)}.tag.ok{background:var(--good)}.portfolio-head{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}.pos{border:1.5px solid #17382e55;border-radius:14px;background:#fffdf7;padding:12px;margin-top:10px;cursor:pointer;transition:transform .12s,box-shadow .12s,border-color .12s}
.pos:hover{transform:translateY(-2px);border-color:var(--line);box-shadow:0 6px 16px rgba(23,56,46,0.15)}
.pos-hint{font-size:11px;color:var(--accent);font-weight:700;margin-top:8px;display:flex;align-items:center;gap:4px}
.modal-backdrop{position:fixed;inset:0;background:rgba(16,37,31,0.65);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px}
.modal-box{background:#fffdf7;border:2px solid var(--line);border-radius:18px;max-width:840px;width:100%;max-height:90vh;overflow-y:auto;padding:22px;box-shadow:0 24px 48px rgba(23,56,46,0.3)}
.modal-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;padding-bottom:12px;border-bottom:2px solid var(--line)}
.modal-close{border:1.5px solid var(--line);background:#fff;border-radius:999px;width:32px;height:32px;font-weight:900;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:16px}
.ladder-badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:800;border:1px solid var(--line)}
.ladder-badge.done{background:#cfe8cf;color:#13221e}
.ladder-badge.active{background:#ffecb3;color:#805b00;outline:2px solid #805b00}
.ladder-badge.next{background:#fff3cd;color:#856404;font-weight:bold}
.ladder-badge.waiting{background:#eee8d9;color:var(--muted)}.pos-head{display:flex;justify-content:space-between;gap:10px;align-items:center}.pos h3{margin:0;font-size:16px}.pos-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}.mini{font-size:12px;color:var(--muted)}.mini b{display:block;color:var(--ink);font-size:14px;margin-top:2px}.pnl-pos{color:#19733a}.pnl-neg{color:#b23a2b}.table-wrap{overflow:auto;border-radius:12px;border:1px solid #17382e33}table{width:100%;border-collapse:collapse;font-size:13px;background:#fffdf7}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #17382e22;white-space:nowrap}th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:#f4eddd;position:sticky;top:0}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:var(--muted)}.warn{border-left:5px solid var(--accent);background:#ffe6d6;padding:10px 12px;border-radius:10px;margin-top:10px}.details{margin-top:10px}details{font-size:12px;color:var(--muted)}summary{cursor:pointer}pre{white-space:pre-wrap;max-height:280px;overflow:auto;background:#fff;border:1px solid #17382e33;border-radius:10px;padding:10px}.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px}.subgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.empty{color:var(--muted);padding:12px}.footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px;color:var(--muted);font-size:12px}
@media(max-width:1200px){.layout,.hero,.subgrid{grid-template-columns:1fr}.kpis,.facts,.portfolio-head{grid-template-columns:repeat(2,1fr)}.agent-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:680px){main{padding:14px}.top{display:block}.toolbar{justify-content:flex-start;margin-top:14px}.kpis,.facts,.portfolio-head,.pos-grid,.agent-grid{grid-template-columns:1fr}.card{padding:12px}}
</style>
</head>
<body>
<main>
  <header class="top">
    <div><p class="eyebrow">OKX read-only / multi-agent desk</p><h1 class="title">AI Agent Desk</h1></div>
    <div class="toolbar">
      <span class="pill" id="p-mode">mode ?</span><span class="pill" id="p-health">worker ?</span><span class="pill" id="p-sync">okx ?</span><span class="pill" id="p-rev">rev ?</span>
      <select id="probe-symbol"><option>BTC-USDT</option><option>ETH-USDT</option><option>SOL-USDT</option><option>BNB-USDT</option><option>XRP-USDT</option></select><button id="probe">Run AI round</button><button id="refresh">Refresh</button>
    </div>
  </header>

  <section class="kpis" id="kpis"></section>

  <div class="layout" style="margin-top:16px">
    <section class="stack">
      <article class="card"><div class="section-title"><h2>Last AI Round</h2><span class="mono muted" id="round-id">-</span></div><div id="last-round"></div></article>
      <article class="card"><div class="section-title"><h2>Agent Votes</h2><span class="muted" id="vote-summary">-</span></div><div id="agent-votes"></div></article>
      <article class="card"><div class="section-title"><h2>Stop-Loss Learning Memory (SL_01, SL_02...)</h2><span class="muted" id="sl-summary">Self-learning database</span></div><div id="sl-memory"></div></article>
      <details class="card"><summary><b>More logs</b> · consensus, agent decisions, market scans</summary><div class="details"><h2>Consensus</h2><div id="consensus"></div><h2 style="margin-top:18px">Agent Decisions</h2><div id="decisions"></div><h2 style="margin-top:18px">Market Scans</h2><div id="ticks"></div></div></details>
    </section>
    <aside class="stack">
      <article class="card"><h2>Real OKX Portfolio</h2><div id="portfolio"></div></article>
      <article class="card"><h2>AI Cost By Agent</h2><div id="agent-cost"></div></article>
    </aside>
  </div>
  <div class="footer"><span id="updated">loading...</span><span id="db-info">db ?</span></div>
  <div id="pos-modal" class="modal-backdrop" style="display:none" onclick="if(event.target===this)closeModal()">
    <div class="modal-box">
      <div class="modal-head">
        <div id="m-title" style="display:flex;align-items:center;gap:10px;font-size:18px;font-weight:900">Chi tiết vị thế</div>
        <button class="modal-close" onclick="closeModal()">✕</button>
      </div>
      <div id="m-body"></div>
    </div>
  </div>
</main>
<script>
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>\"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
const n = (v, d=2) => (v === null || v === undefined || v === "") ? "-" : Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
const usd = (v) => (v === null || v === undefined || v === "") ? "-" : "$" + Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:4});
const tok = (v) => (v === null || v === undefined) ? "-" : Number(v).toLocaleString();
const pct = (v, d=2) => (v === null || v === undefined || v === "") ? "-" : (Number(v)*100).toFixed(d) + "%";
const when = (ts) => ts ? new Date(Number(ts) < 2000000000 ? Number(ts)*1000 : ts).toLocaleString() : "-";
const clsPnl = (v) => Number(v || 0) >= 0 ? "pnl-pos" : "pnl-neg";
function tag(v){ const x=String(v||"hold").toLowerCase(); return "<span class=\"tag " + esc(x) + "\">" + esc(x) + "</span>"; }
function listPositions(p){ const raw=(p||{}).positions||{}; return Array.isArray(raw) ? raw : Object.values(raw); }
function kpi(k,v,s){ return "<div class=\"kpi\"><div class=\"k\">"+esc(k)+"</div><div class=\"v\">"+v+"</div><div class=\"s\">"+s+"</div></div>"; }
function renderKpis(d){
  const totals=d.summary.totals||{}, day=d.summary.last_24h||{}, p=d.portfolio||{}, lr=d.last_ai_round||{}, u=lr.usage||{};
  const positions=listPositions(p), fallback=(d.summary.agents||[]).reduce((a,x)=>a+Number(x.fallback_calls||0),0), calls=(d.summary.agents||[]).reduce((a,x)=>a+Number(x.calls||0),0);
  $("kpis").innerHTML = [
    kpi("OKX equity", usd(p.equity), "cash " + usd(p.available_cash ?? p.cash) + " · PnL <span class=\"" + clsPnl(p.unrealized_pnl) + "\">" + usd(p.unrealized_pnl) + "</span>"),
    kpi("Open positions", n(positions.length,0), esc(p.source||"paper") + " · read-only"),
    kpi("Last AI cost", lr.usage_recorded ? usd(u.estimated_cost_usd) : "-", tok(u.total_tokens) + " tokens · " + n(u.agent_count,0) + " agents"),
    kpi("24h AI spend", usd(day.estimated_cost_usd), n(day.rounds,0) + " rounds · " + tok(day.total_tokens) + " tokens"),
    kpi("All-time cost", usd(totals.estimated_cost_usd), tok(totals.total_tokens) + " tokens"),
    kpi("AI rounds", n(totals.rounds,0), tok(totals.agent_calls) + " agent calls"),
    kpi("Fallbacks", n(fallback,0), "of " + n(calls,0) + " calls"),
    kpi("Audit DB", (d.audit_backend||{}).kind === "postgres" ? "Postgres" : "SQLite", esc((d.audit_backend||{}).target||"-"))
  ].join("");
}
function closeModal(){
  $("pos-modal").style.display = "none";
}
document.addEventListener("keydown", function(e){
  if(e.key === "Escape") closeModal();
});
function openPosModal(idx){
  const x = (window.currentPositions || [])[idx];
  if(!x) return;
  const entry = Number(x.entry_price || 0);
  const mark = Number(x.mark_price || entry);
  const side = String(x.side || "long").toLowerCase();
  const isShort = side.includes("short") || side.includes("sell");
  const lever = Number(x.leverage || 35);
  const margin = Number(x.margin || 3.5);
  const notional = Number(x.position_value || (margin * lever));
  const decimals = (x.symbol && x.symbol.includes("BTC")) ? 1 : ((x.symbol && x.symbol.includes("XRP")) ? 4 : 2);
  const curStage = Number(x.trailing_stage || 0);
  const curSL = Number(x.stop_loss || 0);
  const curTP = Number(x.take_profit || 0);
  const initSL = Number(x.initial_sl || curSL);

  function calcPnl(targetPx){
    if(!targetPx || !entry) return { usd: 0, roe: 0, pct: 0 };
    const diff = isShort ? (entry - targetPx) : (targetPx - entry);
    const p = diff / entry;
    return { usd: notional * p, roe: p * lever * 100, pct: p * 100 };
  }
  function roundDec(val, dec){
    const factor = Math.pow(10, dec);
    return Math.round(val * factor) / factor;
  }

  const bePrice = roundDec(isShort ? entry * (1 - 0.0015) : entry * (1 + 0.0015), decimals);
  const ladder = x.tp_ladder || {};
  const tp1 = ladder.tp1 || roundDec(isShort ? entry * (1 - 0.006) : entry * (1 + 0.006), decimals);
  const tp2 = ladder.tp2 || roundDec(isShort ? entry * (1 - 0.010) : entry * (1 + 0.010), decimals);
  const tp3 = ladder.tp3 || roundDec(isShort ? entry * (1 - 0.015) : entry * (1 + 0.015), decimals);
  const tp4 = ladder.tp4 || roundDec(isShort ? entry * (1 - 0.022) : entry * (1 + 0.022), decimals);
  const tp5 = ladder.tp5 || roundDec(isShort ? entry * (1 - 0.030) : entry * (1 + 0.030), decimals);
  const tp6 = ladder.tp6 || roundDec(isShort ? entry * (1 - 0.040) : entry * (1 + 0.040), decimals);
  const tp7 = ladder.tp7 || roundDec(isShort ? entry * (1 - 0.050) : entry * (1 + 0.050), decimals);

  const stages = [
    {
      stage: 0,
      name: "Khởi tạo (Initial Setup)",
      triggerDesc: "Giá Entry: " + n(entry, decimals),
      triggerPx: entry,
      slDesc: "SL ban đầu (" + n(initSL, decimals) + ")",
      slPnl: calcPnl(initSL),
      tpDesc: "TP ban đầu (" + n(curTP || tp3, decimals) + ")",
      tpPnl: calcPnl(curTP || tp3),
      note: "Bảo vệ vốn ban đầu"
    },
    {
      stage: 1,
      name: "Nấc 1: Hòa vốn (Breakeven)",
      triggerDesc: "Chạm TP1 (+0.60%): " + n(tp1, decimals),
      triggerPx: tp1,
      slDesc: "Dời về Hòa vốn + phí (" + n(bePrice, decimals) + ")",
      slPnl: calcPnl(bePrice),
      tpDesc: "Duy trì TP3 (" + n(tp3, decimals) + ")",
      tpPnl: calcPnl(tp3),
      note: "Khóa lãi an toàn +0.15% (không còn rủi ro lỗ)"
    },
    {
      stage: 2,
      name: "Nấc 2: Khóa lãi TP1",
      triggerDesc: "Chạm TP2 (+1.00%): " + n(tp2, decimals),
      triggerPx: tp2,
      slDesc: "Khóa cứng SL tại TP1 (" + n(tp1, decimals) + ")",
      slPnl: calcPnl(tp1),
      tpDesc: "Nới TP lên TP4 (" + n(tp4, decimals) + ")",
      tpPnl: calcPnl(tp4),
      note: "Khóa chắc lợi nhuận +0.60% (+21% ROE)"
    },
    {
      stage: 3,
      name: "Nấc 3: Khóa lãi TP2",
      triggerDesc: "Chạm TP3 (+1.50%): " + n(tp3, decimals),
      triggerPx: tp3,
      slDesc: "Khóa cứng SL tại TP2 (" + n(tp2, decimals) + ")",
      slPnl: calcPnl(tp2),
      tpDesc: "Nới TP lên TP5 (" + n(tp5, decimals) + ")",
      tpPnl: calcPnl(tp5),
      note: "Khóa chắc lợi nhuận +1.00% (+35% ROE)"
    },
    {
      stage: 4,
      name: "Nấc 4: Khóa lãi TP3",
      triggerDesc: "Chạm TP4 (+2.20%): " + n(tp4, decimals),
      triggerPx: tp4,
      slDesc: "Khóa cứng SL tại TP3 (" + n(tp3, decimals) + ")",
      slPnl: calcPnl(tp3),
      tpDesc: "Nới TP lên TP6 (" + n(tp6, decimals) + ")",
      tpPnl: calcPnl(tp6),
      note: "Khóa chắc lợi nhuận +1.50% (+52.5% ROE)"
    },
    {
      stage: 5,
      name: "Nấc 5: Khóa lãi TP4",
      triggerDesc: "Chạm TP5 (+3.00%): " + n(tp5, decimals),
      triggerPx: tp5,
      slDesc: "Khóa cứng SL tại TP4 (" + n(tp4, decimals) + ")",
      slPnl: calcPnl(tp4),
      tpDesc: "Nới TP lên TP7 (" + n(tp7, decimals) + ")",
      tpPnl: calcPnl(tp7),
      note: "Khóa chắc lợi nhuận +2.20% (+77% ROE)"
    }
  ];

  const nextSt = stages.find(s => s.stage === curStage + 1);
  let banner = "";
  if(nextSt){
    const diffPx = Math.abs(mark - nextSt.triggerPx);
    const diffPct = (diffPx / mark) * 100;
    const dirText = isShort ? "giảm thêm" : "tăng thêm";
    banner = "<div class=\"warn\" style=\"margin-top:0;margin-bottom:14px;background:#eef6ee;border-color:#19733a;color:#13221e\">" +
      "🎯 <b>Mục tiêu dời SL kế tiếp:</b> Giá cần " + dirText + " <b>" + n(diffPx, decimals) + " giá (" + n(diffPct, 2) + "%)</b> để chạm <b>" + esc(nextSt.triggerDesc) + "</b>. " +
      "Khi đó bot sẽ tự động dời SL lên <b>" + esc(nextSt.slDesc) + "</b> để bảo toàn <b>" + (nextSt.slPnl.usd >= 0 ? "+" : "") + usd(nextSt.slPnl.usd) + " (" + (nextSt.slPnl.roe >= 0 ? "+" : "") + n(nextSt.slPnl.roe, 1) + "% ROE)</b>!</div>";
  }

  $("m-title").innerHTML = esc(x.symbol) + " " + tag(x.side) + " <span class=\"pill\" style=\"font-size:11px\">" + n(lever, 0) + "x Isolated</span>";

  let mHtml = "<div class=\"kpis\" style=\"grid-template-columns:repeat(4,1fr);margin-bottom:14px\">" +
    "<div class=\"kpi\"><div class=\"k\">Giá Entry</div><div class=\"v\" style=\"font-size:17px\">" + n(entry, decimals) + "</div></div>" +
    "<div class=\"kpi\"><div class=\"k\">Giá Hiện tại</div><div class=\"v\" style=\"font-size:17px\">" + n(mark, decimals) + "</div></div>" +
    "<div class=\"kpi\"><div class=\"k\">Lãi/Lỗ Thả nổi</div><div class=\"v " + clsPnl(x.unrealized_pnl) + "\" style=\"font-size:17px\">" + usd(x.unrealized_pnl) + " (" + n((x.unrealized_pnl_pct||0) * 100, 2) + "%)</div></div>" +
    "<div class=\"kpi\"><div class=\"k\">Nấc Hiện tại</div><div class=\"v\" style=\"font-size:17px\">Stage " + curStage + "</div><div class=\"s\">" + (curStage >= 2 ? ("Khóa lãi TP" + (curStage - 1)) : (curStage === 1 ? "Hòa vốn" : "Ban đầu")) + "</div></div>" +
    "</div>" + banner +
    "<div class=\"table-wrap\">" +
    "<table class=\"ladder-table\">" +
    "<thead><tr>" +
    "<th>Giai đoạn</th>" +
    "<th>Giá kích hoạt</th>" +
    "<th>Mức dời SL mới</th>" +
    "<th class=\"num\">Lãi khóa khi dính SL</th>" +
    "<th>Mức nới TP mới</th>" +
    "<th class=\"num\">Lãi tối đa tại TP</th>" +
    "<th>Trạng thái</th>" +
    "</tr></thead><tbody>" +
    stages.map(st => {
      const isDone = st.stage < curStage;
      const isActive = st.stage === curStage;
      const isNext = st.stage === curStage + 1;
      let badge = "";
      if(isDone) badge = "<span class=\"ladder-badge done\">✓ Đã đạt</span>";
      else if(isActive) badge = "<span class=\"ladder-badge active\">▶ Đang áp dụng</span>";
      else if(isNext) badge = "<span class=\"ladder-badge next\">🎯 Mục tiêu tới</span>";
      else badge = "<span class=\"ladder-badge waiting\">Chờ kích hoạt</span>";

      const trClass = isActive ? "style=\"background:#fff9e6;font-weight:600\"" : (isNext ? "style=\"background:#fbfbfb\"" : "");
      const slCol = st.slPnl.usd > 0 ? "pnl-pos" : (st.slPnl.usd < 0 ? "pnl-neg" : "");
      return "<tr " + trClass + ">" +
        "<td><b>" + esc(st.name) + "</b></td>" +
        "<td>" + esc(st.triggerDesc) + "</td>" +
        "<td>" + esc(st.slDesc) + "</td>" +
        "<td class=\"num " + slCol + "\"><b>" + (st.slPnl.usd >= 0 ? "+" : "") + usd(st.slPnl.usd) + "</b><br><small>(" + (st.slPnl.roe >= 0 ? "+" : "") + n(st.slPnl.roe, 1) + "% ROE)</small></td>" +
        "<td>" + esc(st.tpDesc) + "</td>" +
        "<td class=\"num pnl-pos\"><b>+" + usd(st.tpPnl.usd) + "</b><br><small>(+" + n(st.tpPnl.roe, 1) + "% ROE)</small></td>" +
        "<td>" + badge + "</td>" +
        "</tr>";
    }).join("") +
    "</tbody></table></div>" +
    "<div style=\"margin-top:12px;font-size:12px;color:var(--muted);line-height:1.45\">" +
    "💡 <i>Ghi chú:</i> Bot tự động gửi lệnh điều kiện OCO lên sàn OKX sửa SL & TP theo từng nấc ngay khi giá thị trường chạm mốc tương ứng, đảm bảo bảo toàn lợi nhuận tối đa mà không cần can thiệp thủ công." +
    "</div>";

  $("m-body").innerHTML = mHtml;
  $("pos-modal").style.display = "flex";
}
function renderPortfolio(p){
  if(!p || p.available===false){ $("portfolio").innerHTML="<div class=\"empty\">Worker not available.</div>"; return; }
  const positions=listPositions(p);
  window.currentPositions=positions;
  const head="<div class=\"portfolio-head\">"+
    kpi("Equity", usd(p.equity), "account value")+kpi("Cash", usd(p.available_cash ?? p.cash), "available")+
    kpi("Floating PnL", "<span class=\""+clsPnl(p.unrealized_pnl)+"">"+usd(p.unrealized_pnl)+"</span>", "unrealized")+
    kpi("Margin used", usd(p.margin_used), "read from OKX")+"</div>";
  const rows=positions.length ? positions.map((x,idx)=>"<div class=\"pos\" onclick=\"openPosModal("+idx+")\" title=\"Nhấp để xem chi tiết lộ trình dời TP/SL\"><div class=\"pos-head\"><h3>"+esc(x.symbol)+"</h3><div style=\"display:flex;gap:6px;align-items:center\">"+tag(x.side)+"<span class=\"tag ok\" style=\"font-size:10px;cursor:pointer\">🔍 Nấc TP/SL</span></div></div><div class="pos-grid">"+
    "<div class=\"mini\">Qty<b>"+n(x.quantity,6)+"</b></div><div class=\"mini\">Entry<b>"+n(x.entry_price,6)+"</b></div><div class=\"mini\">Mark<b>"+n(x.mark_price,6)+"</b></div><div class=\"mini\">PnL<b class=\""+clsPnl(x.unrealized_pnl)+"">"+usd(x.unrealized_pnl)+"</b></div>"+
    "<div class=\"mini\">Margin<b>"+usd(x.margin)+"</b></div><div class=\"mini\">Lev<b>"+n(x.leverage,0)+"x</b></div><div class=\"mini\">SL<b>"+(x.stop_loss ? n(x.stop_loss, 2) : "-")+"</b></div><div class=\"mini\">TP<b>"+(x.take_profit ? n(x.take_profit, 2) : "-")+"</b></div>"+
    "<div class=\"mini\">Stage<b>"+(x.trailing_stage >= 2 ? ("Locked TP" + (x.trailing_stage - 1)) : (x.trailing_stage === 1 ? "Breakeven" : "Initial"))+"</b></div><div class=\"mini\">Opened<b>"+esc(x.opened_at||"-")+"</b></div>"+
    "</div><div class=\"pos-hint\">🔍 Nhấp vào để xem chi tiết các nấc dời TP/SL & Lãi/Lỗ tương ứng</div></div>").join("") : "<div class=\"empty\">No open positions.</div>";
  $("portfolio").innerHTML=head+"<div class=\"muted mono\">synced "+esc(p.synced_at||"-")+" · "+esc(p.source||"-")+"</div>"+rows;
}
function renderLastRound(r, prices){
  if(!r){ $("last-round").innerHTML="<div class=\"empty\">No AI round recorded.</div>"; return; }
  const c=r.consensus||{}, u=r.usage||{}, det=r.deterministic||{}, agents=r.agents||[];
  const buys=agents.filter(a=>a.action==="buy").length;
  const sells=agents.filter(a=>a.action==="sell").length;
  const holds=agents.filter(a=>a.action==="hold").length;
  const veto=agents.filter(a=>a.veto).length;
  const vetoAgents=agents.filter(a=>a.veto).map(a=>a.agent);
  $("round-id").textContent = (r.round_id||"-") + " · " + (r.symbol||c.symbol||"-");
  const hero="<div class=\"hero\"><div class=\"verdict "+esc(c.action||"hold")+"\"><div class=\"action\">"+esc(c.action||"hold")+"</div><div>approved <b>"+(c.approved?"YES":"NO")+"</b></div><div class=\"muted\">score <b>"+n(c.score,3)+"</b> / 0.580</div></div>"+
    "<div><div class=\"facts\">"+
    "<div class=\"fact\"><b>Cost</b><span>"+(r.usage_recorded?usd(u.estimated_cost_usd):"-")+"</span></div>"+
    "<div class=\"fact\"><b>Tokens</b><span>"+tok(u.total_tokens)+"</span></div>"+
    "<div class=\"fact\"><b>Votes</b><span>"+buys+" buy · "+sells+" sell · "+holds+" hold · "+veto+" veto</span></div>"+
    "<div class=\"fact\"><b>Last call</b><span>"+when(c.ts)+"</span></div>"+
    "<div class=\"fact\"><b>Score (Target ≥ 0.580)</b><span>"+n(c.score,3)+" / 0.580</span></div>"+
    "<div class=\"fact\"><b>Reasons</b><span>"+esc((c.reason_codes&&c.reason_codes.length)?c.reason_codes.join(", "):(c.approved?"Approved":(veto>0?"Vetoed by "+vetoAgents.join(", "):((buys===8||sells===8)?"Score "+n(c.score,3)+" < 0.580":"Score "+n(c.score,3)+" / No consensus"))))+"</span></div>"+
    "</div></div></div>";
  let warn = "";
  const slMatch = (c.reason_codes||[]).find(x => x && (x.includes("SL_") || x.includes("sl_") || x.includes("similar_to")));
  if(c.approved){
    warn = "<div class=\"warn ok-warn\" style=\"background:#d6ead5;border-color:#19733a;color:#13221e\"><b>APPROVED FOR LIVE TRADE!</b> Score <b>"+n(c.score,3)+"</b> ≥ 0.580 threshold with 8/8 consensus. Live order sent to OKX.</div>";
  } else if(slMatch){
    const cid = (slMatch.match(/SL_\d+/i) || [slMatch])[0].toUpperCase();
    warn = "<div class=\"warn\" style=\"border-left-color:#b23a2b;background:#ffe6e6\"><b>🚫 TỰ HỌC TỪ CHỐI (VETO "+esc(cid)+").</b> Tín hiệu vào lệnh trùng mô hình dính SL trước đó (<b>"+esc(cid)+"</b>). AI chặn vào lệnh để bảo vệ vốn.</div>";
  } else if(veto > 0){
    warn = "<div class=\"warn\"><b>NOT APPROVED (Vetoed).</b> Vetoed by <b>"+veto+" agent(s)</b>: "+esc(vetoAgents.join(", "))+". Need 0 veto and score ≥ 0.580 to enter.</div>";
  } else if(buys === 8 || sells === 8){
    const diff = Math.max(0, 0.58 - Number(c.score||0)).toFixed(3);
    warn = "<div class=\"warn\"><b>NOT APPROVED (Score < 0.580).</b> All 8 agents voted <b>"+(buys===8?"BUY":"SELL")+"</b>, but total Score is <b>"+n(c.score,3)+"</b> (Below required threshold <b>0.580</b>). Need +"+diff+" more confidence score to enter.</div>";
  } else {
    warn = "<div class=\"warn\"><b>NOT APPROVED.</b> Votes: "+buys+" buy, "+sells+" sell, "+holds+" hold, "+veto+" veto. Need 8/8 consensus & score ≥ 0.580 to enter.</div>";
  }
  $("last-round").innerHTML=hero+warn;
}
function renderAgentVotes(r, prices){
  const agents=(r&&r.agents)||[]; if(!agents.length){ $("agent-votes").innerHTML="<div class=\"empty\">No agent rows.</div>"; return; }
  const c=(r&&r.consensus)||{};
  const buys=agents.filter(a=>a.action==="buy").length, sells=agents.filter(a=>a.action==="sell").length, holds=agents.filter(a=>a.action==="hold").length, veto=agents.filter(a=>a.veto).length;
  $("vote-summary").textContent = buys+" buy · "+sells+" sell · "+holds+" hold · "+veto+" veto · Score: "+n(c.score,3)+" / 0.580 ("+(c.approved?"APPROVED":"NOT APPROVED")+")";
  $("agent-votes").innerHTML="<div class=\"agent-grid\">"+agents.map(a=>{
    const now=prices[a.symbol]?prices[a.symbol].price:null, delta=(now&&a.entry_price)?(now/a.entry_price-1)*100:null;
    return "<div class=\"agent "+(a.veto?"veto\">":"\">")+"<div class=\"name\"><span>"+esc(a.agent)+"</span>"+tag(a.action)+"</div><div class=\"meta\">conf "+n(a.confidence,2)+" · "+esc(a.data_quality||"-")+(a.veto?" · veto":"")+"<br>entry "+n(a.entry_price)+" · SL "+n(a.stop_loss_price)+" · TP "+n(a.take_profit_price)+"<br>now Δ "+(delta===null?"-":delta.toFixed(3)+"%")+"</div><details><summary>reasons</summary><pre>"+esc((a.reason_codes||[]).join("\n")||"-")+"</pre></details></div>";
  }).join("")+"</div>";
}
function renderAgentCost(agents){
  agents=agents||[]; if(!agents.length){ $("agent-cost").innerHTML="<div class=\"empty\">No AI calls yet.</div>"; return; }
  const max=Math.max(...agents.map(a=>Number(a.estimated_cost_usd||0)),1e-9);
  $("agent-cost").innerHTML="<div class=\"table-wrap\"><table><thead><tr><th>Agent</th><th class=\"num\">Calls</th><th class=\"num\">Cost</th><th class=\"num\">Veto</th><th>Share</th></tr></thead><tbody>"+agents.map(a=>"<tr><td><b>"+esc(a.agent)+"</b></td><td class=\"num\">"+n(a.calls,0)+"</td><td class=\"num\">"+usd(a.estimated_cost_usd)+"</td><td class=\"num\">"+n(a.veto_calls,0)+"</td><td><div class=\"bar\"><i style=\"width:"+Math.round(Number(a.estimated_cost_usd||0)/max*100)+"%\"></i></div></td></tr>").join("")+"</tbody></table></div>";
}
function renderConsensus(rows){
  rows=rows||[];
  $("consensus").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>When</th><th>Symbol</th><th>Setup Signal</th><th>Final Action</th><th class=\"num\">Score</th><th>Approved</th><th>Why Not Entered / Reasons</th></tr></thead><tbody>"+rows.slice(0,25).map(r=>{
    const votes=r.votes||[];
    const vetoes=votes.filter(v=>v.veto).map(v=>v.agent_name);
    const buys=votes.filter(v=>v.action==="buy").length;
    const sells=votes.filter(v=>v.action==="sell").length;
    let explanation = "";
    const reasons = r.reason_codes || [];
    const slMatch = reasons.find(x => x && (x.includes("SL_") || x.includes("sl_") || x.includes("similar_to")));
    if(slMatch){
      const cid = (slMatch.match(/SL_\d+/i) || [slMatch])[0].toUpperCase();
      explanation = "🚫 VETO: Trùng mô hình " + cid;
    } else if(reasons.includes("position_already_exists")){
      explanation = "Position already open (" + (r.symbol||"") + ")";
    } else if(reasons.includes("proposal_required_margin_exceeds_available_cash")){
      explanation = "Insufficient cash for required margin (5u)";
    } else if(reasons.includes("deterministic_hold")){
      explanation = "No conservative technical setup";
    } else if(reasons.includes("ai_advisory_cooldown")){
      explanation = "AI Advisory Cooldown active";
    } else if(!r.approved){
      if(vetoes.length) explanation = "VETO by " + vetoes.join(", ");
      else if(buys === 8 || sells === 8) explanation = "Score " + n(r.score,3) + " < 0.580 threshold";
      else explanation = reasons.length ? reasons.filter(x=>x!=="ai_precheck_skipped").join(", ") : ("Score " + n(r.score,3) + " / No consensus");
    } else {
      explanation = "Approved & Executed";
    }
    const det = r.deterministic_decision || r.deterministic || {};
    const setupAction = det.action || "hold";
    return "<tr><td>"+when(r.ts)+"</td><td>"+esc(r.symbol)+"</td><td>"+tag(setupAction)+"</td><td>"+tag(r.action)+"</td><td class=\"num\"><b>"+n(r.score,3)+"</b> / 0.580</td><td>"+(r.approved?"<span class=\"tag buy\">YES</span>":"<span class=\"tag bad\">NO</span>")+"</td><td>"+esc(explanation)+"</td></tr>";
  }).join("")+"</tbody></table></div>":"<div class=\"empty\">No consensus rows.</div>";
}
function renderLossesMemory(rows){
  rows=rows||[];
  $("sl-summary").textContent=rows.length?(rows.length+" cases indexed"):"No recent losses";
  $("sl-memory").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>Case ID</th><th>Symbol</th><th>Side</th><th class=\"num\">Exit Px</th><th class=\"num\">Loss (USDT)</th><th class=\"num\">Age</th><th>Learned Avoidance Rule</th></tr></thead><tbody>"+rows.map(r=>"<tr><td><b class=\"tag bad\">"+esc(r.case_id||"SL")+"</b></td><td>"+esc(r.symbol)+"</td><td>"+tag(r.direction||r.side)+"</td><td class=\"num\">"+n(r.exit_price)+"</td><td class=\"num pnl-neg\">"+usd(r.net_loss_usdt)+"</td><td class=\"num\">"+n(r.loss_age_minutes,0)+"m ago</td><td style=\"font-size:11px;color:var(--muted);white-space:normal;\">"+esc(r.rule||"")+"</td></tr>").join("")+"</tbody></table></div>":"<div class=\"empty\">No recent stop-loss cases within 48h. Bot trading clean.</div>";
}
function renderDecisions(rows){ rows=rows||[]; $("decisions").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>When</th><th>Agent</th><th>Symbol</th><th>Action</th><th>Quality</th><th>Veto</th><th class=\"num\">Entry</th><th class=\"num\">Cost</th></tr></thead><tbody>"+rows.slice(0,80).map(r=>"<tr><td>"+when(r.ts)+"</td><td>"+esc(r.agent_name)+"</td><td>"+esc(r.symbol)+"</td><td>"+tag(r.action)+"</td><td>"+esc(r.data_quality)+"</td><td>"+(r.veto?"yes":"no")+"</td><td class=\"num\">"+n(r.entry_price)+"</td><td class=\"num\">"+usd(r.estimated_cost_usd)+"</td></tr>").join("")+"</tbody></table></div>":"<div class=\"empty\">No decisions.</div>"; }
function renderTicks(rows){ rows=rows||[]; $("ticks").innerHTML=rows.length?"<div class=\"table-wrap\"><table><thead><tr><th>When</th><th>Symbol</th><th class=\"num\">Price</th><th>Action</th><th>Reason</th><th class=\"num\">RSI</th></tr></thead><tbody>"+rows.slice(0,80).map(r=>"<tr><td>"+when(r.ts)+"</td><td>"+esc(r.symbol)+"</td><td class=\"num\">"+n(r.price)+"</td><td>"+tag(r.action)+"</td><td>"+esc(r.reason)+"</td><td class=\"num\">"+n(r.rsi,1)+"</td></tr>").join("")+"</tbody></table></div>":"<div class=\"empty\">No market scans.</div>"; }
async function load(){
  try{
    const res=await fetch("/api/dashboard?limit=200",{cache:"no-store"}); const d=await res.json(); if(d.error){throw new Error(d.error+" "+(d.detail||""));}
    const rt=d.runtime||{}, caps=rt.capabilities||{}, okx=rt.okx_account||{}, backend=d.audit_backend||{};
    $("p-mode").textContent="mode "+((rt.runtime||{}).mode||"?"); $("p-health").textContent=d.health.paper_worker?"worker healthy":"worker degraded"; $("p-health").className="pill "+(d.health.paper_worker?"ok":"bad");
    $("p-sync").textContent=okx.synced?"OKX synced":"OKX not synced"; $("p-sync").className="pill "+(okx.synced?"ok":"bad"); $("p-rev").textContent="rev "+String(rt.code_revision||"unknown").slice(0,8);
    renderKpis(d); renderPortfolio(d.portfolio); renderLastRound(d.last_ai_round,d.last_prices||{}); renderAgentVotes(d.last_ai_round,d.last_prices||{}); renderAgentCost(d.summary.agents); renderLossesMemory(d.recent_losses_memory); renderConsensus(d.events.consensus); renderDecisions(d.events.agent_decision); renderTicks(d.events.paper_tick);
    $("db-info").textContent="db "+(backend.kind||"?")+" · live="+caps.live_trading+" · paper_exec="+caps.paper_execution+" · read_only="+caps.okx_read_only; $("updated").textContent="updated "+new Date().toLocaleTimeString()+" · last tick "+(d.health.last_tick_at?when(d.health.last_tick_at):"never");
  }catch(error){ $("updated").textContent="dashboard error: "+error; $("last-round").innerHTML="<div class=\"warn\"><b>Dashboard error.</b> "+esc(String(error))+"</div>"; }
}
$("refresh").addEventListener("click",load);
$("probe").addEventListener("click",async()=>{ const symbol=$("probe-symbol").value; if(!confirm("Call all 8 OpenAI agents now for "+symbol+"?\n\nThis spends real API tokens and is written to the audit log.")){return;} $("probe").disabled=true; $("probe").textContent="running..."; try{ const res=await fetch("/api/ai/probe?symbol="+encodeURIComponent(symbol),{method:"POST"}); const d=await res.json(); if(!d.available){alert("AI round unavailable: "+(d.reason||res.status));} else {alert("AI round "+symbol+"\nconsensus="+d.action+" approved="+d.approved+"\ntokens="+tok(d.ai_usage.total_tokens)+" cost="+usd(d.ai_usage.estimated_cost_usd));} await load(); }catch(error){alert("AI round failed: "+error);} finally{$("probe").disabled=false; $("probe").textContent="Run AI round";} });
load(); setInterval(load,10000);
</script>
</body>
</html>
"""