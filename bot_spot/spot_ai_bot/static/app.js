const els = {
  statusText: document.querySelector("#statusText"),
  envText: document.querySelector("#envText"),
  budgetText: document.querySelector("#budgetText"),
  exchangeText: document.querySelector("#exchangeText"),
  exchangeConfigText: document.querySelector("#exchangeConfigText"),
  modelText: document.querySelector("#modelText"),
  openaiText: document.querySelector("#openaiText"),
  modePill: document.querySelector("#modePill"),
  sidebarModeText: document.querySelector("#sidebarModeText"),
  stripMode: document.querySelector("#stripMode"),
  stripExchange: document.querySelector("#stripExchange"),
  stripBudget: document.querySelector("#stripBudget"),
  stripGuard: document.querySelector("#stripGuard"),
  sessionStatus: document.querySelector("#sessionStatus"),
  symbolsText: document.querySelector("#symbolsText"),
  scanSummary: document.querySelector("#scanSummary"),
  dataSourceBanner: document.querySelector("#dataSourceBanner"),
  lastScanAt: document.querySelector("#lastScanAt"),
  bestTrend: document.querySelector("#bestTrend"),
  bestLiquidity: document.querySelector("#bestLiquidity"),
  lowestVolatility: document.querySelector("#lowestVolatility"),
  candidateCount: document.querySelector("#candidateCount"),
  marketCards: document.querySelector("#marketCards"),
  groupedScanGrid: document.querySelector("#groupedScanGrid"),
  topScoreRows: document.querySelector("#topScoreRows"),
  watchlistCount: document.querySelector("#watchlistCount"),
  watchlistRows: document.querySelector("#watchlistRows"),
  marketRows: document.querySelector("#marketRows"),
  configList: document.querySelector("#configList"),
  riskGuard: document.querySelector("#riskGuard"),
  allocationBar: document.querySelector("#allocationBar"),
  allocationSource: document.querySelector("#allocationSource"),
  executedMode: document.querySelector("#executedMode"),
  totalProposed: document.querySelector("#totalProposed"),
  riskBlocks: document.querySelector("#riskBlocks"),
  proposalList: document.querySelector("#proposalList"),
  thesisSummaryText: document.querySelector("#thesisSummaryText"),
  thesisGrid: document.querySelector("#thesisGrid"),
  latestRunText: document.querySelector("#latestRunText"),
  runBadge: document.querySelector("#runBadge"),
  activityLog: document.querySelector("#activityLog"),
  toast: document.querySelector("#toast"),
  themeBtn: document.querySelector("#themeBtn"),
  refreshBtn: document.querySelector("#refreshBtn"),
  scanBtn: document.querySelector("#scanBtn"),
  runBtn: document.querySelector("#runBtn"),
  careBtn: document.querySelector("#careBtn"),
};

const activity = [];
let previousScanPrices = loadPreviousScanPrices();
let dashboardConfig = {
  signal_trend_threshold: 0.65,
  signal_liquidity_threshold: 0.70,
  signal_max_volatility: 0.80,
  shortlist_min_observations_for_trade: 2,
  shortlist_min_age_minutes_for_trade: 30,
};

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("dashboardTheme", theme);
  els.themeBtn.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
}

function initTheme() {
  const saved = localStorage.getItem("dashboardTheme");
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
}

function money(value) {
  const number = Number(value || 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(number);
}

function coinPrice(value) {
  const number = Number(value || 0);
  if (!number) return "$0";
  if (number < 0.000001) return `$${number.toPrecision(3)}`;
  if (number < 1) {
    return `$${number.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 8,
    })}`;
  }
  return money(number);
}

function pct(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function changePct(value) {
  const number = Number(value || 0);
  const formatted = Number.isInteger(number)
    ? String(number)
    : number.toFixed(2).replace(/\.?0+$/, "");
  return `${formatted}%`;
}

function loadPreviousScanPrices() {
  try {
    return JSON.parse(sessionStorage.getItem("previousScanPrices") || "{}");
  } catch {
    return {};
  }
}

function savePreviousScanPrices(candidates) {
  const prices = {};
  for (const candidate of candidates) {
    prices[candidate.symbol] = Number(candidate.price || 0);
  }
  sessionStorage.setItem("previousScanPrices", JSON.stringify(prices));
  previousScanPrices = prices;
}

function scanChangePct(candidate) {
  const previous = Number(previousScanPrices[candidate.symbol] || 0);
  const current = Number(candidate.price || 0);
  if (!previous || !current) return null;
  return ((current - previous) / previous) * 100;
}

function renderChange(label, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return `<em class="change-new">${label}: má»›i</em>`;
  }
  const cls = Number(value) >= 0 ? "change-up" : "change-down";
  return `<em class="${cls}">${label}: ${changePct(value)}</em>`;
}

function nowTime() {
  return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}

function formatLocalDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("vi-VN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function elapsedTime(value) {
  if (!value) return "-";
  const started = new Date(value);
  if (Number.isNaN(started.getTime())) return "-";
  const seconds = Math.max(0, Math.floor((Date.now() - started.getTime()) / 1000));
  if (seconds < 60) return `${seconds} giay`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phut`;
  const hours = Math.floor(minutes / 60);
  const remainMinutes = minutes % 60;
  if (hours < 24) return remainMinutes ? `${hours} gio ${remainMinutes} phut` : `${hours} gio`;
  const days = Math.floor(hours / 24);
  const remainHours = hours % 24;
  return remainHours ? `${days} ngay ${remainHours} gio` : `${days} ngay`;
}

function reasonLabel(value) {
  const map = {
    mat_tinh_hinh_thi_truong_dang_chu_y: "Thi truong dang chu y",
    noteworthy_market_move: "Bien dong dang chu y",
    bien_dong_manh_can_theo_doi: "Bien dong manh can theo doi",
    chua_du_muc_do_quan_tam: "Chua du muc do quan tam",
  };
  return map[String(value || "")] || String(value || "-");
}

function readinessLabel(item) {
  if (item.trade_ready) {
    return `<span class="readiness ready">Trade-ready</span><small>${item.observation_count || 1} lan xac nhan</small>`;
  }
  return `<span class="readiness waiting">Cho xac nhan</span><small>${item.readiness_reason || "Can them tin hieu/thoi gian"}</small>`;
}
function renderScanChange(label, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return `<em class="change-new">${label}: m\u1edbi</em>`;
  }
  const cls = Number(value) >= 0 ? "change-up" : "change-down";
  return `<em class="${cls}">${label}: ${changePct(value)}</em>`;
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  setTimeout(() => els.toast.classList.remove("show"), 2600);
}

function logActivity(title, detail) {
  activity.unshift({ time: nowTime(), title, detail });
  activity.splice(5);
  els.activityLog.innerHTML = activity.map((item) => `
    <div class="activity-item">
      <span>${item.time}</span>
      <div><strong>${item.title}</strong><span>${item.detail}</span></div>
    </div>
  `).join("");
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function renderScore(value) {
  const width = Math.max(0, Math.min(100, Number(value || 0) * 100));
  return `
    <span class="score">
      <span>${pct(value)}</span>
      <span class="track"><span class="fill" style="width:${width}%"></span></span>
    </span>
  `;
}

function signalFor(candidate) {
  if (
    candidate.trend_score >= dashboardConfig.signal_trend_threshold
    && candidate.liquidity_score >= dashboardConfig.signal_liquidity_threshold
    && candidate.volatility_score <= dashboardConfig.signal_max_volatility
  ) {
    return { label: "Candidate", cls: "" };
  }
  return { label: "Watch", cls: "wait" };
}

function compositeScore(candidate) {
  return (
    Number(candidate.trend_score || 0) * 0.45
    + Number(candidate.liquidity_score || 0) * 0.35
    + (1 - Number(candidate.volatility_score || 0)) * 0.20
  );
}

function sectorLabel(value) {
  const map = {
    layer1: "Layer 1",
    layer2: "Layer 2",
    ai: "AI",
    defi: "DeFi",
    meme: "Meme",
    infra: "Infra",
    stable: "Stable",
    other: "Other",
  };
  return map[String(value || "other").toLowerCase()] || "Other";
}

function sectorFromSymbol(symbol) {
  const normalized = String(symbol || "").replace("-", "").replace("/", "").toUpperCase();
  const base = normalized.endsWith("USDT") ? normalized.slice(0, -4) : normalized;
  const sets = {
    "Layer 1": ["BTC", "ETH", "SOL", "BNB", "ADA", "AVAX", "DOT", "ATOM", "NEAR", "SUI", "APT", "TON", "TRX", "XRP", "LTC", "BCH", "SEI", "INJ"],
    "Layer 2": ["ARB", "OP", "STRK", "IMX", "MATIC", "POL", "ZK", "STX"],
    AI: ["FET", "RENDER", "RNDR", "WLD", "ARKM", "AIOZ", "IO", "AGIX", "OCEAN", "NMR", "TAO"],
    DeFi: ["UNI", "AAVE", "CRV", "COMP", "MKR", "LDO", "SNX", "DYDX", "PENDLE", "GMX"],
    Meme: ["DOGE", "SHIB", "PEPE", "BONK", "FLOKI", "WIF", "BRETT", "PENGU"],
    Infra: ["LINK", "FIL", "AR", "TIA", "HNT", "GRT"],
    Stable: ["USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE"],
  };
  return Object.entries(sets).find(([, values]) => values.includes(base))?.[0] || "Other";
}

function sectorClass(group) {
  return `sector-${String(group || "other").toLowerCase().replace(/\s+/g, "-")}`;
}

function renderGroupedScans(candidates) {
  const groups = new Map();
  for (const candidate of candidates) {
    const group = candidate.metadata?.crypto_sector
      ? sectorLabel(candidate.metadata.crypto_sector)
      : sectorFromSymbol(candidate.symbol);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(candidate);
  }

  const order = ["Layer 1", "Layer 2", "AI", "DeFi", "Meme", "Infra", "Stable", "Other"];
  const blocks = order
    .filter((group) => (groups.get(group) || []).length)
    .map((group) => {
      const top = [...groups.get(group)]
        .sort((a, b) => Number(b.metadata?.change_pct || 0) - Number(a.metadata?.change_pct || 0))
        .slice(0, 5);
      return `
        <article class="group-card ${sectorClass(group)}">
          <div class="group-headline">
            <strong>${group}</strong>
            <small>${top.length} coin(s)</small>
          </div>
          <div class="group-list">
            ${top.map((candidate) => `
              <div class="group-row">
                <span>
                  <b>${candidate.symbol}</b>
                  <small>${coinPrice(candidate.price)}</small>
                </span>
                <span class="change-stack">
                  ${renderScanChange("24h", candidate.metadata?.change_pct)}
                  ${renderScanChange("Scan", scanChangePct(candidate))}
                </span>
              </div>
            `).join("")}
          </div>
        </article>
      `;
    });

  els.groupedScanGrid.innerHTML = blocks.length
    ? blocks.join("")
    : `
      <div class="empty-state">
        <strong>No grouped scan yet</strong>
        <span>Run a scan to see the strongest coins per sector.</span>
      </div>
    `;
}

function renderTopScores(candidates) {
  const ranked = [...candidates]
    .map((candidate) => ({
      ...candidate,
      score: compositeScore(candidate),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);

  if (!ranked.length) {
    els.topScoreRows.innerHTML = `<tr><td colspan="6">No scan yet.</td></tr>`;
    return;
  }

  els.topScoreRows.innerHTML = ranked.map((candidate, index) => `
    <tr>
      <td><strong>${index + 1}</strong></td>
      <td>
        <strong>${candidate.symbol}</strong>
        <div class="score-sector">${sectorLabel(candidate.metadata?.crypto_sector || sectorFromSymbol(candidate.symbol))}</div>
      </td>
      <td>${candidate.score.toFixed(4)}</td>
      <td>${candidate.metadata?.candlestick_pattern || "-"}</td>
      <td>
        <span class="${Number(candidate.metadata?.change_pct || 0) >= 0 ? "change-up" : "change-down"}">
          ${changePct(candidate.metadata?.change_pct)}
        </span>
      </td>
      <td>
        <span class="${Number(scanChangePct(candidate) || 0) >= 0 ? "change-up" : "change-down"}">
          ${scanChangePct(candidate) === null ? "m\u1edbi" : changePct(scanChangePct(candidate))}
        </span>
      </td>
    </tr>
  `).join("");
}

function renderWatchlist(payload) {
  const items = payload?.items || [];
  const readyCount = items.filter((item) => item.trade_ready).length;
  els.watchlistCount.textContent = `${readyCount}/${items.length} ready`;
  if (!items.length) {
    els.watchlistRows.innerHTML = `<tr><td colspan="6">Chua co cap nao trong watchlist.</td></tr>`;
    return;
  }

  els.watchlistRows.innerHTML = items.map((item) => `
    <tr>
      <td><strong>#${item.priority || "-"}</strong></td>
      <td>
        <strong>${item.exchange_symbol || item.symbol || "-"}</strong>
        <div class="score-sector">Diem ${Number(item.score || 0).toFixed(4)}</div>
      </td>
      <td>${reasonLabel(item.reason)}</td>
      <td>${readinessLabel(item)}</td>
      <td>${elapsedTime(item.created_at)}</td>
      <td>${formatLocalDateTime(item.expires_at)}</td>
    </tr>
  `).join("");
}

function renderState(state) {
  const { health, config } = state;
  dashboardConfig = { ...dashboardConfig, ...config };
  els.statusText.textContent = health.status;
  els.envText.textContent = `${health.env} environment`;
  els.budgetText.textContent = money(config.budget_usd);
  els.exchangeText.textContent = health.exchange;
  els.exchangeConfigText.textContent = config.exchange_configured ? "API keys configured" : "API keys missing";
  els.modelText.textContent = health.model;
  els.openaiText.textContent = config.openai_configured ? "OpenAI configured" : "Fallback advisor active";
  els.symbolsText.textContent = config.market_symbols;
  els.modePill.textContent = health.live_trading ? "LIVE" : "PAPER";
  els.modePill.className = `pill ${health.live_trading ? "status-danger" : ""}`;
  els.sidebarModeText.textContent = health.live_trading
    ? `Live mode capped at ${money(config.max_live_trade_usd)} per trade.`
    : "Paper mode is active. Orders are simulated.";
  els.stripMode.textContent = health.live_trading ? "LIVE" : "PAPER";
  els.stripExchange.textContent = health.exchange;
  els.stripBudget.textContent = money(config.budget_usd);
  els.stripGuard.textContent = config.auto_scan_enabled ? `Scan ${config.scan_interval_seconds}s` : "Scan off";

  renderConfig(config);
  renderRiskGuard(health, config);
}

function renderConfig(config) {
  const rows = [
    ["MongoDB", config.mongodb_configured, "Decision logs"],
    ["OpenAI", config.openai_configured, "AI advisor"],
    ["Telegram", config.telegram_configured, "Notifications"],
    ["Exchange API", config.exchange_configured, "Live execution"],
    ["OKX Passphrase", config.okx_passphrase_configured, "Private API"],
    ["Auto Scan", config.auto_scan_enabled, `${config.scan_interval_seconds}s interval`],
    ["Scan Storage", config.store_all_scans, config.store_all_scans ? "Store every scan" : `Signal + heartbeat / ${config.scan_heartbeat_store_interval}`],
    ["Approval Required", config.approval_required, "Manual guard"],
  ];
  els.configList.innerHTML = rows.map(([label, ok, detail]) => `
    <div class="config-row">
      <span>${label}<small>${detail}</small></span>
      <strong class="${ok ? "status-ok" : "status-warn"}">${ok ? "Ready" : "Not set"}</strong>
    </div>
  `).join("");
}

function renderRiskGuard(health, config) {
  const rows = [
    ["Execution Mode", health.live_trading ? "Live" : "Paper", health.live_trading ? "status-danger" : "status-ok"],
    ["Per Trade Cap", money(config.max_live_trade_usd), "status-ok"],
    ["Signal Trend", `>= ${pct(config.signal_trend_threshold)}`, "status-ok"],
    ["Signal Liquidity", `>= ${pct(config.signal_liquidity_threshold)}`, "status-ok"],
    ["Signal Volatility", `<= ${pct(config.signal_max_volatility)}`, "status-ok"],
    ["Watchlist Confirm", `${config.shortlist_min_observations_for_trade}x or ${config.shortlist_min_age_minutes_for_trade}m`, "status-ok"],
    ["Market Regime", config.market_regime_enabled ? config.market_regime_symbols : "Disabled", config.market_regime_enabled ? "status-ok" : "status-warn"],
    ["Anti Pump", `24h < ${changePct(config.anti_pump_max_24h_change_pct)}`, "status-ok"],
    ["Telegram Approval", config.approval_required ? "Required" : "Optional", config.approval_required ? "status-ok" : "status-warn"],
    ["Exchange Keys", config.exchange_configured ? "Present" : "Missing", config.exchange_configured ? "status-ok" : "status-warn"],
    ["OKX Passphrase", config.okx_passphrase_configured ? "Present" : "Missing", config.okx_passphrase_configured ? "status-ok" : "status-warn"],
  ];
  els.riskGuard.innerHTML = rows.map(([label, value, cls]) => `
    <div class="risk-row">
      <span>${label}</span>
      <b class="${cls}">${value}</b>
    </div>
  `).join("");
}

function renderMarket(candidates, result = {}) {
  els.scanSummary.innerHTML = `<strong>${candidates.length}</strong><small>candidates</small>`;
  const live = result.data_source === "live";
  els.dataSourceBanner.className = `data-source-banner ${live ? "live" : "fallback"}`;
  els.dataSourceBanner.textContent = live
    ? `LIVE market data from ${String(result.exchange || "").toUpperCase()} public API.`
    : `Fallback sample data. ${result.fallback_reason || "Exchange data was unavailable."}`;
  els.lastScanAt.textContent = `Last scan: ${formatLocalDateTime(result.last_scan_at)}`;
  if (!candidates.length) {
    els.marketCards.innerHTML = "";
    els.groupedScanGrid.innerHTML = `
      <div class="empty-state">
        <strong>No grouped scan yet</strong>
        <span>Run a scan to see the strongest coins per sector.</span>
      </div>
    `;
    els.topScoreRows.innerHTML = `<tr><td colspan="6">No scan yet.</td></tr>`;
    els.marketRows.innerHTML = `<tr><td colspan="7">No candidates returned.</td></tr>`;
    els.bestTrend.textContent = "-";
    els.bestLiquidity.textContent = "-";
    els.lowestVolatility.textContent = "-";
    els.candidateCount.textContent = "0";
    return;
  }

  const bestTrend = [...candidates].sort((a, b) => b.trend_score - a.trend_score)[0];
  const bestLiquidity = [...candidates].sort((a, b) => b.liquidity_score - a.liquidity_score)[0];
  const lowestVolatility = [...candidates].sort((a, b) => a.volatility_score - b.volatility_score)[0];
  const tradeCandidates = candidates.filter((candidate) => signalFor(candidate).label === "Candidate");
  els.bestTrend.textContent = `${bestTrend.symbol} ${pct(bestTrend.trend_score)}`;
  els.bestLiquidity.textContent = `${bestLiquidity.symbol} ${pct(bestLiquidity.liquidity_score)}`;
  els.lowestVolatility.textContent = `${lowestVolatility.symbol} ${pct(lowestVolatility.volatility_score)}`;
  els.candidateCount.textContent = String(tradeCandidates.length);

  els.marketCards.innerHTML = candidates.slice(0, 4).map((candidate) => `
    <div class="market-tile">
      <div>
        <strong>${candidate.symbol}</strong>
        <small>${money(candidate.price)}</small>
      </div>
      <div class="mini-bars" aria-hidden="true">
        <i style="height:${Math.max(8, candidate.trend_score * 46)}px"></i>
        <i style="height:${Math.max(8, candidate.liquidity_score * 46)}px"></i>
        <i style="height:${Math.max(8, candidate.volatility_score * 46)}px"></i>
      </div>
    </div>
  `).join("");
  renderGroupedScans(candidates);
  renderTopScores(candidates);

  els.marketRows.innerHTML = candidates.map((candidate) => {
    const signal = signalFor(candidate);
    return `
      <tr>
        <td><strong>${candidate.symbol}</strong></td>
        <td>${money(candidate.price)}</td>
        <td>${renderScore(candidate.trend_score)}</td>
        <td>${renderScore(candidate.liquidity_score)}</td>
        <td>${renderScore(candidate.volatility_score)}</td>
        <td><span class="signal ${signal.cls}">${signal.label}</span></td>
        <td>${candidate.metadata?.change_pct ?? "-"}</td>
      </tr>
    `;
  }).join("");
}

function renderRunGuardSummary(run) {
  const regime = run.market_regime || {};
  const skipped = run.skipped_candidate_count || 0;
  const tradeReady = run.trade_ready_symbols || [];
  const skippedRows = (run.skipped_candidates || []).slice(0, 8).map((item) => `
    <div class="guard-item">
      <strong>${item.symbol}</strong>
      <span>${item.reason}</span>
    </div>
  `).join("");
  return `
    <div class="guard-summary">
      <div class="guard-item">
        <strong>${regime.ok === false ? "Market regime blocked" : "Market regime ok"}</strong>
        <span>${regime.reason || "-"}</span>
      </div>
      <div class="guard-item">
        <strong>${tradeReady.length} trade-ready</strong>
        <span>${tradeReady.length ? tradeReady.join(", ") : "No watchlist pair is ready for buy rules."}</span>
      </div>
      <div class="guard-item">
        <strong>${skipped} skipped</strong>
        <span>Skipped before AI/proposal because guard rules were not satisfied.</span>
      </div>
      ${skippedRows}
    </div>
  `;
}

function renderRun(run) {
  sessionStorage.setItem("latestRun", JSON.stringify(run));
  els.latestRunText.textContent = `${run.proposal_count} proposal(s) created at ${nowTime()}`;
  els.runBadge.textContent = run.proposal_count ? "Review" : "No trades";
  els.runBadge.className = `pill ${run.proposal_count ? "" : "muted-pill"}`;
  const allocation = run.allocation?.allocation || {};
  const total = Number(run.allocation?.total_budget_usd || 0);
  const proposed = run.proposals.reduce((sum, proposal) => sum + Number(proposal.amount_usd || 0), 0);
  const blocked = run.proposals.filter((proposal) => String(proposal.status || "").includes("blocked") || String(proposal.status || "").includes("rejected")).length;
  els.allocationSource.textContent = run.allocation?.reason?.toLowerCase().includes("fallback") ? "Fallback" : "AI";
  els.executedMode.textContent = run.proposals.some((proposal) => String(proposal.status || "").startsWith("live")) ? "Live" : "Paper";
  els.totalProposed.textContent = money(proposed);
  els.riskBlocks.textContent = String(blocked);

  els.allocationBar.innerHTML = Object.entries(allocation).map(([group, value]) => {
    const width = total ? Math.max(0, Math.min(100, Number(value) / total * 100)) : 0;
    return `
      <div class="allocation-piece">
        <div>
          <strong>${money(value)}</strong>
          <small>${group}</small>
        </div>
        <div class="allocation-track"><div class="allocation-fill" style="width:${width}%"></div></div>
      </div>
    `;
  }).join("");

  if (!run.proposals.length) {
    els.proposalList.innerHTML = `
      <div class="empty-state">
        <strong>No proposal passed the filters</strong>
        <span>Watchlist persistence, market regime, anti-pump, trend, liquidity, or risk guards blocked new buys.</span>
      </div>
      ${renderRunGuardSummary(run)}
    `;
    return;
  }

  els.proposalList.innerHTML = `
    ${renderRunGuardSummary(run)}
    ${run.proposals.map((proposal) => `
    <div class="proposal">
      <div class="proposal-title">
        <strong>${proposal.action} ${proposal.symbol}</strong>
        <small>${proposal.advisor?.opinion || "advisor n/a"} - ${proposal.strategy_reason}</small>
      </div>
      <div>${money(proposal.amount_usd)}<small>Amount</small></div>
      <div>${money(proposal.price)}<small>Price</small></div>
      <div>${proposal.quantity || "-"}<small>Quantity</small></div>
      <div>${proposal.status}<small>${proposal.risk_notes?.length ? proposal.risk_notes.join(", ") : "Risk ok"}</small></div>
    </div>
  `).join("")}
  `;
}

function renderTheses(payload) {
  const items = payload?.items || [];
  els.thesisSummaryText.textContent = `${items.length} thesis record(s) loaded.`;
  if (!items.length) {
    els.thesisGrid.innerHTML = `
      <div class="empty-state">
        <strong>No trade thesis yet</strong>
        <span>Watchlist care will create thesis records for active watchlist pairs.</span>
      </div>
    `;
    return;
  }
  els.thesisGrid.innerHTML = items.map((item) => {
    const zone = item.buy_zone || {};
    const tp = item.take_profit_zones_usdt || [];
    return `
      <article class="thesis-card">
        <div class="thesis-head">
          <strong>${item.exchange_symbol || item.symbol}</strong>
          <span class="readiness ${item.status === "buy_zone" ? "ready" : "waiting"}">${item.status || "-"}</span>
        </div>
        <p>${item.status_reason || item.thesis || "-"}</p>
        <div class="thesis-metrics">
          <span>Price <b>${coinPrice(item.current_price_usdt)}</b></span>
          <span>Support <b>${coinPrice(item.support_usdt)}</b></span>
          <span>Invalid <b>${coinPrice(item.invalidation_price_usdt)}</b></span>
          <span>TP <b>${tp.map((value) => coinPrice(value)).join(", ") || "-"}</b></span>
        </div>
        <small>${zone.reason || "no zone"} | v${item.version || 1} | ${formatLocalDateTime(item.updated_at)}</small>
      </article>
    `;
  }).join("");
}

async function refreshTheses() {
  try {
    renderTheses(await api("/watchlist/theses"));
  } catch (error) {
    logActivity("Thesis refresh failed", error.message);
  }
}

function restoreLatestRun() {
  const saved = sessionStorage.getItem("latestRun");
  if (!saved) return;
  try {
    renderRun(JSON.parse(saved));
  } catch {
    sessionStorage.removeItem("latestRun");
  }
}

async function refreshState() {
  els.refreshBtn.disabled = true;
  els.sessionStatus.textContent = "Refreshing";
  try {
    renderState(await api("/dashboard/state"));
    logActivity("Dashboard refreshed", "Health, configuration, and risk guard were updated.");
    toast("Dashboard refreshed");
  } catch (error) {
    logActivity("Refresh failed", error.message);
    toast(`Refresh failed: ${error.message}`);
  } finally {
    els.sessionStatus.textContent = "Ready";
    els.refreshBtn.disabled = false;
  }
}

async function scanMarket() {
  els.scanBtn.disabled = true;
  els.sessionStatus.textContent = "Scanning";
  try {
    const result = await api("/market/scan");
    renderMarket(result.candidates || [], result);
    try {
      renderWatchlist(await api("/market/shortlist"));
    } catch (watchlistError) {
      logActivity("Watchlist failed", watchlistError.message);
    }
    savePreviousScanPrices(result.candidates || []);
    logActivity("Market scanned", `${result.candidate_count} candidate(s) returned from ${result.data_source || "unknown"} data.`);
    toast(`Scanned ${result.candidate_count} candidate(s)`);
  } catch (error) {
    logActivity("Scan failed", error.message);
    toast(`Scan failed: ${error.message}`);
  } finally {
    els.sessionStatus.textContent = "Ready";
    els.scanBtn.disabled = false;
  }
}

async function runOnce() {
  els.runBtn.disabled = true;
  els.sessionStatus.textContent = "Running cycle";
  try {
    const result = await api("/run-once", { method: "POST" });
    renderRun(result);
    logActivity("Bot cycle completed", `${result.proposal_count} proposal(s) created.`);
    toast("Bot cycle completed");
  } catch (error) {
    logActivity("Run failed", error.message);
    toast(`Run failed: ${error.message}`);
  } finally {
    els.sessionStatus.textContent = "Ready";
    els.runBtn.disabled = false;
  }
}

async function runCareLoop() {
  els.careBtn.disabled = true;
  els.sessionStatus.textContent = "Caring watchlist";
  try {
    const result = await api("/watchlist/care", { method: "POST" });
    await refreshTheses();
    logActivity("Watchlist care completed", `${result.count || 0} thesis event(s) updated.`);
    toast("Watchlist care completed");
  } catch (error) {
    logActivity("Watchlist care failed", error.message);
    toast(`Care failed: ${error.message}`);
  } finally {
    els.sessionStatus.textContent = "Ready";
    els.careBtn.disabled = false;
  }
}

els.refreshBtn.addEventListener("click", refreshState);
els.scanBtn.addEventListener("click", scanMarket);
els.runBtn.addEventListener("click", runOnce);
els.careBtn.addEventListener("click", runCareLoop);
els.themeBtn.addEventListener("click", () => {
  const current = document.documentElement.dataset.theme || "light";
  applyTheme(current === "dark" ? "light" : "dark");
});

initTheme();
restoreLatestRun();
refreshState().then(scanMarket).then(refreshTheses);

