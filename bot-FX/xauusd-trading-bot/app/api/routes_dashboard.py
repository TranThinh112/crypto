"""Small browser dashboard for monitoring the trading bot."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate" />
  <title>Trading Bot Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #080b10;
      --panel: #111821;
      --panel-2: #0d131b;
      --border: #223041;
      --text: #e6edf3;
      --muted: #8796a8;
      --green: #00c087;
      --red: #f6465d;
      --amber: #f0b90b;
      --blue: #4da3ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: radial-gradient(circle at top left, #102033 0, var(--bg) 36%);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .wrap { max-width: 1560px; margin: 0 auto; padding: 22px; }
    header {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      margin-bottom: 18px;
    }
    h1 { margin: 0; font-size: 24px; letter-spacing: .2px; }
    .sub { color: var(--muted); margin-top: 4px; font-size: 13px; }
    .pill {
      border: 1px solid var(--border); background: rgba(17, 24, 33, .8);
      padding: 8px 11px; border-radius: 999px; color: var(--muted); font-size: 13px;
      white-space: nowrap;
    }
    .grid { display: grid; gap: 14px; }
    .cards { grid-template-columns: repeat(6, minmax(0, 1fr)); margin-bottom: 14px; }
    .basket-row { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 14px; }
    .card-actions { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
    .card-actions button { padding: 6px 10px; border-radius: 999px; font-size: 12px; }
    .card, .panel {
      background: linear-gradient(180deg, rgba(17, 24, 33, .94), rgba(13, 19, 27, .94));
      border: 1px solid var(--border); border-radius: 16px;
      box-shadow: 0 18px 60px rgba(0, 0, 0, .28);
    }
    .card { padding: 15px; min-height: 96px; }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .label-row { display: flex; align-items: center; gap: 6px; }
    .help-dot {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      border: 1px solid var(--border);
      border-radius: 50%;
      color: var(--muted);
      background: rgba(77, 163, 255, .08);
      font-size: 11px;
      font-weight: 800;
      cursor: help;
      text-transform: none;
      letter-spacing: 0;
    }
    .help-tooltip {
      position: fixed;
      width: min(360px, calc(100vw - 24px));
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #000;
      color: #fff;
      border-color: rgba(255, 255, 255, .28);
      box-shadow: 0 18px 45px rgba(0, 0, 0, .72);
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      opacity: 0;
      pointer-events: none;
      transform: translateY(4px);
      transition: opacity .12s ease, transform .12s ease;
      z-index: 10000;
    }
    .help-tooltip.open {
      opacity: 1;
      transform: translateY(0);
    }
    .help-dot:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
    .mode-help {
      margin-left: 6px;
      width: 16px;
      height: 16px;
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      background: rgba(8, 11, 16, .28);
      font-size: 11px;
      font-weight: 800;
      line-height: 1;
      flex: 0 0 auto;
    }
    button.active .mode-help { color: var(--amber); border-color: rgba(240, 185, 11, .34); }
    .mode-label {
      border: 1px solid var(--border);
      background: rgba(17, 24, 33, .8);
      padding: 8px 11px;
      border-radius: 10px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .mode-label.soft { color: var(--amber); border-color: rgba(240, 185, 11, .45); background: rgba(240, 185, 11, .1); }
    .mode-label.hard { color: var(--red); border-color: rgba(246, 70, 93, .45); background: rgba(246, 70, 93, .1); }
    .mode-label.normal { color: var(--green); border-color: rgba(0, 192, 135, .35); background: rgba(0, 192, 135, .08); }
    .mode-label .mode-help { margin-left: 6px; }
    .value { margin-top: 9px; font-size: 24px; font-weight: 750; }
    .hint { margin-top: 7px; font-size: 12px; color: var(--muted); }
    .positive { color: var(--green); }
    .negative { color: var(--red); }
    .amber { color: var(--amber); }
    .blue { color: var(--blue); }
    .panel { overflow: hidden; }
    .panel-head {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      padding: 14px 16px; border-bottom: 1px solid var(--border);
    }
    .panel-title { font-weight: 700; }
    .panel-meta { color: var(--muted); font-size: 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 11px 12px; border-bottom: 1px solid rgba(34, 48, 65, .7); text-align: left; font-size: 13px; }
    th { color: var(--muted); font-weight: 650; background: rgba(8, 11, 16, .28); }
    tr:hover td { background: rgba(77, 163, 255, .05); }
    .num {
      text-align: right;
      font-variant-numeric: tabular-nums;
      font-family: "Cascadia Mono", "Consolas", monospace;
    }
    .badge {
      display: inline-flex; align-items: center; justify-content: center;
      padding: 4px 8px; border-radius: 999px; font-weight: 700; font-size: 12px;
      background: rgba(135, 150, 168, .14); color: var(--muted);
    }
    .buy { background: rgba(0, 192, 135, .14); color: var(--green); }
    .sell { background: rgba(246, 70, 93, .14); color: var(--red); }
    .open { background: rgba(77, 163, 255, .14); color: var(--blue); }
    .closed { background: rgba(135, 150, 168, .14); color: var(--muted); }
    .failed, .rejected { background: rgba(246, 70, 93, .14); color: var(--red); }
    .two-col { grid-template-columns: 1.1fr .9fr; }
    .stats-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .stats-table {
      table-layout: fixed;
      min-width: 640px;
    }
    .stats-table th,
    .stats-table td {
      height: 54px;
      padding-top: 8px;
      padding-bottom: 8px;
      vertical-align: middle;
    }
    .stats-table th:first-child,
    .stats-table td:first-child {
      width: 120px;
      white-space: nowrap;
    }
    .stats-toggle-row {
      cursor: pointer;
      user-select: none;
    }
    .stats-toggle-row td:first-child {
      color: var(--blue);
      font-weight: 800;
    }
    .stats-toggle-row:hover td { background: rgba(77, 163, 255, .08); }
    .stats-child-row td:first-child {
      padding-left: 28px;
      color: var(--muted);
    }
    .modal-overlay {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 26px;
      background: rgba(3, 7, 12, .72);
      backdrop-filter: blur(8px);
      z-index: 1000;
    }
    .modal-overlay.open { display: flex; }
    .modal-panel {
      width: min(1480px, 98vw);
      max-height: 88vh;
      display: flex;
      flex-direction: column;
      background: linear-gradient(180deg, rgba(17, 24, 33, .98), rgba(13, 19, 27, .98));
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 24px 90px rgba(0, 0, 0, .5);
      overflow: hidden;
    }
    .modal-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
    }
    .modal-close {
      width: 34px;
      height: 34px;
      padding: 0;
      border-radius: 50%;
      font-size: 22px;
      line-height: 1;
    }
    .modal-body {
      min-height: 0;
      overflow: auto;
      padding: 14px 16px 18px;
    }
    .modal-section-title {
      margin: 14px 0 8px;
      font-weight: 800;
    }
    #forex-stats-modal .panel-title,
    #forex-stats-modal .modal-section-title,
    #forex-stats-modal td,
    #forex-stats-modal .type-cell,
    #forex-stats-modal .symbol-name {
      color: var(--text);
    }
    #forex-stats-modal .panel-meta,
    #forex-stats-modal th,
    #forex-stats-modal .wr-cell small {
      color: var(--muted);
    }
    #forex-stats-modal .modal-stats-table td:first-child {
      color: var(--text);
      font-weight: 750;
    }
    .time-short {
      white-space: nowrap;
      cursor: help;
      color: var(--text);
    }
    .forex-history-table {
      table-layout: fixed;
      min-width: 1460px;
    }
    .forex-history-table th,
    .forex-history-table td {
      text-align: center;
      vertical-align: middle;
      padding-left: 8px;
      padding-right: 8px;
    }
    .forex-history-table th:nth-child(1), .forex-history-table td:nth-child(1) { width: 4%; }
    .forex-history-table th:nth-child(2), .forex-history-table td:nth-child(2) { width: 8%; }
    .forex-history-table th:nth-child(3), .forex-history-table td:nth-child(3) { width: 8%; }
    .forex-history-table th:nth-child(4), .forex-history-table td:nth-child(4) { width: 5%; }
    .forex-history-table th:nth-child(5), .forex-history-table td:nth-child(5) { width: 9%; }
    .forex-history-table th:nth-child(6), .forex-history-table td:nth-child(6) { width: 6%; }
    .forex-history-table th:nth-child(7), .forex-history-table td:nth-child(7) { width: 7%; }
    .forex-history-table th:nth-child(8), .forex-history-table td:nth-child(8) { width: 6%; }
    .forex-history-table th:nth-child(9), .forex-history-table td:nth-child(9) { width: 5%; }
    .forex-history-table th:nth-child(10), .forex-history-table td:nth-child(10),
    .forex-history-table th:nth-child(11), .forex-history-table td:nth-child(11),
    .forex-history-table th:nth-child(12), .forex-history-table td:nth-child(12) { width: 6%; }
    .forex-history-table th:nth-child(13), .forex-history-table td:nth-child(13) { width: 7%; }
    .forex-history-table th:nth-child(14), .forex-history-table td:nth-child(14) { width: 10%; }
    .forex-history-table th:nth-child(15), .forex-history-table td:nth-child(15) { width: 11%; }
    .forex-history-table .symbol-cell {
      justify-content: center;
    }
    .forex-history-table .type-cell,
    .forex-history-table .time-short,
    .forex-history-table .close-reason {
      display: inline-block;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .close-reason {
      padding: 4px 7px;
      border-radius: 8px;
      font-weight: 800;
      font-size: 12px;
      line-height: 1;
      background: rgba(135, 150, 168, .14);
      color: var(--muted);
    }
    .close-reason.tp,
    .close-reason.bw { background: rgba(0, 192, 135, .14); color: var(--green); }
    .close-reason.bw { background: rgba(0, 128, 72, .22); color: #00d27a; }
    .close-reason.sld { background: rgba(0, 192, 135, .14); color: var(--green); }
    .close-reason.bvl { background: rgba(245, 158, 11, .22); color: #f59e0b; }
    .close-reason.sl { background: rgba(246, 70, 93, .14); color: var(--red); }
    .close-reason.bl { background: rgba(240, 185, 11, .18); color: var(--amber); }
    .stats-panel {
      display: flex;
      flex-direction: column;
      min-height: 310px;
      overflow: hidden;
    }
    .learning-panel {
      height: 360px;
      min-height: 360px;
      max-height: 360px;
    }
    .stats-panel .scroll {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      overflow-x: auto;
    }
    .daily-stats-scroll {
      flex: 0 0 270px;
      height: 270px;
      max-height: 270px;
    }
    .daily-stats-scroll th {
      position: sticky;
      top: 0;
      z-index: 2;
    }
    .learning-stats-section {
      margin-top: 26px !important;
    }
    .monitor-grid { grid-template-columns: 1fr; align-items: start; }
    .positions-scroll { overflow-x: hidden; max-height: 520px; }
    .positions-table {
      table-layout: fixed;
      min-width: 0;
      width: 100%;
    }
    .positions-table th,
    .positions-table td {
      padding: 8px 7px;
      font-size: 11px;
      vertical-align: middle;
      overflow: hidden;
    }
    .positions-table th.num,
    .positions-table td.num { text-align: right; }
    .positions-table th:nth-child(1),
    .positions-table td:nth-child(1),
    .positions-table th:nth-child(2),
    .positions-table td:nth-child(2),
    .positions-table th:nth-child(6),
    .positions-table td:nth-child(6) { text-align: left; }
    .positions-table th:nth-child(3),
    .positions-table td:nth-child(3),
    .positions-table th:nth-child(7),
    .positions-table td:nth-child(7) { text-align: center; }
    .positions-table th:nth-child(8),
    .positions-table td:nth-child(8),
    .positions-table th:nth-child(9),
    .positions-table td:nth-child(9),
    .positions-table th:nth-child(10),
    .positions-table td:nth-child(10),
    .positions-table th:nth-child(11),
    .positions-table td:nth-child(11),
    .positions-table th:nth-child(12),
    .positions-table td:nth-child(12),
    .positions-table th:nth-child(13),
    .positions-table td:nth-child(13) { text-align: right; }
    .positions-table th:nth-child(4),
    .positions-table td:nth-child(4),
    .positions-table th:nth-child(5),
    .positions-table td:nth-child(5) { text-align: center; }
    .positions-table th.left,
    .positions-table td.left { text-align: left; }
    .positions-table th.center,
    .positions-table td.center { text-align: center; }
    .positions-table td.num {
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-variant-numeric: tabular-nums;
    }
    .positions-table .badge {
      padding: 3px 6px;
      font-size: 11px;
    }
    .positions-table th,
    .positions-table td,
    .positions-table th.num,
    .positions-table td.num,
    .positions-table th.left,
    .positions-table td.left,
    .positions-table th.center,
    .positions-table td.center {
      text-align: center !important;
    }
    .positions-table .symbol-cell {
      justify-content: center;
    }
    .positions-table .type-cell,
    .positions-table .time-cell {
      text-align: center;
    }
    .positions-table td:first-child { text-align: center; }
    .positions-table .badge {
      margin-left: auto;
      margin-right: auto;
    }
    .positions-table .price-cell,
    .positions-table .price-pnl {
      align-items: center;
      justify-content: center;
      text-align: center;
    }
    .type-cell {
      display: block;
      line-height: 1.15;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .symbol-cell {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      white-space: nowrap;
      max-width: 100%;
      justify-content: flex-start;
    }
    .symbol-logo {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 10px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.18);
      flex: 0 0 auto;
    }
    .symbol-logo.btc { background: linear-gradient(135deg, #f7931a, #ffbd59); color: #111; font-size: 0; }
    .symbol-logo.btc::before { content: "\\20BF"; font-size: 10px; }
    .symbol-logo.gold { background: linear-gradient(135deg, #f0b90b, #ffe18a); color: #181000; font-size: 9px; }
    .symbol-logo.forex {
      background: linear-gradient(135deg, #2a6f97, #61d4b3);
      color: #061016;
      font-size: 8px;
      letter-spacing: 0;
    }
    .symbol-logo.forex.jpy { background: linear-gradient(135deg, #c43b4d, #ffd166); color: #17080b; }
    .symbol-logo.forex.chf { background: linear-gradient(135deg, #d90429, #f8f9fa); color: #1a0b0f; }
    .symbol-logo.generic { background: #263241; color: var(--muted); }
    .symbol-cell > span:last-child,
    .symbol-name {
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .price-pnl {
      display: inline-flex;
      flex-direction: column;
      align-items: flex-end;
      justify-content: center;
      gap: 1px;
      white-space: nowrap;
      line-height: 1.05;
      font-family: "Cascadia Mono", "Consolas", monospace;
      width: 100%;
      min-height: 30px;
    }
    .price-pnl small { font-size: 10px; min-height: 11px; line-height: 1.05; }
    .price-cell {
      display: inline-flex;
      align-items: center;
      justify-content: flex-end;
      width: 100%;
      min-height: 30px;
      white-space: nowrap;
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-variant-numeric: tabular-nums;
    }
    .wr-cell {
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      gap: 1px;
      white-space: nowrap;
      line-height: 1.1;
      font-variant-numeric: tabular-nums;
      font-family: "Cascadia Mono", "Consolas", monospace;
      width: 100%;
    }
    .wr-cell small { color: var(--muted); font-size: 9px; }
    .time-cell { white-space: nowrap; font-size: 11px !important; }
    .signal-panel { border-radius: 14px; }
    .signal-panel .panel-head { padding: 10px 12px; gap: 6px; }
    .signal-panel .panel-title { font-size: 12px; white-space: nowrap; }
    .signal-panel .panel-meta { font-size: 11px; }
    .signal-content { padding: 10px 12px; height: calc(100% - 45px); min-height: 0; }
    .signal-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 18px; height: 100%; min-height: 0; }
    .signal-main { display: grid; grid-template-columns: 1fr; gap: 13px; align-content: start; min-width: 0; }
    .signal-reason { min-width: 0; overflow: hidden; }
    .signal-reason > div:first-child { margin-bottom: 13px; }
    .signal-value { margin-top: 3px; font-size: 14px; font-weight: 750; color: var(--text); line-height: 1.25; }
    .signal-reason .hint { max-height: 104px; overflow: auto; word-break: break-word; font-size: 14px !important; font-weight: 750; color: var(--text); line-height: 1.25; }
    .signal-panel .label { font-size: 10px; }
    .signal-panel .value { margin-top: 3px; font-size: 13px !important; }
    .signal-panel .hint { font-size: 11px !important; line-height: 1.32; }
    .empty { padding: 28px 16px; color: var(--muted); text-align: center; }
    .scroll { overflow: auto; max-height: 520px; }
    .positions-scroll { overflow-x: hidden; overflow-y: auto; }
    .improvement-panel { margin-top: 14px; overflow: visible; }
    .improvement-panel.top { margin-top: 0; margin-bottom: 14px; }
    .improvement-range-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
    .improvement-range-tab {
      padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border);
      background: rgba(255,255,255,.03); color: var(--muted); font-size: 12px; cursor: pointer;
    }
    .improvement-range-tab.active {
      color: var(--text); border-color: rgba(77, 163, 255, .55); background: rgba(77, 163, 255, .12);
    }
    .improvement-body { padding: 14px 16px 16px; }
    .improvement-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .improvement-item {
      min-height: 128px; border: 1px solid rgba(43, 55, 70, .8); border-radius: 8px;
      padding: 10px; background: rgba(8, 11, 16, .18);
    }
    .improvement-item h3 { margin: 0 0 8px; font-size: 14px; }
    .improvement-item .metric { margin-top: 8px; font-size: 22px; font-weight: 800; }
    .metric-row { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
    .delta { font-size: 12px; font-weight: 800; white-space: nowrap; }
    .watch { color: var(--amber); font-weight: 900; }
    .improvement-facts { display: grid; gap: 7px; margin-top: 8px; font-size: 12px; }
    .improvement-facts div { display: flex; justify-content: space-between; gap: 10px; }
    .improvement-facts span { color: var(--muted); }
    .improvement-facts strong { color: var(--text); }
    .improvement-compare-btn {
      border-color: rgba(240, 185, 11, .55);
      color: var(--amber);
      background: rgba(240, 185, 11, .10);
      font-weight: 800;
    }
    .compare-table th,
    .compare-table td {
      text-align: center;
      vertical-align: middle;
      color: var(--text);
    }
    .compare-table th { color: var(--muted); }
    .compare-table .positive { color: var(--green); }
    .compare-table .negative { color: var(--red); }
    .compare-table .amber { color: var(--amber); }
    .compare-table th:first-child,
    .compare-table td:first-child {
      text-align: left;
      width: auto;
    }
    .compare-note {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .compare-tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .compare-tab {
      padding: 7px 10px;
      border-radius: 8px;
      font-size: 12px;
    }
    .compare-tab.active {
      color: var(--text);
      border-color: rgba(77, 163, 255, .55);
      background: rgba(77, 163, 255, .12);
    }
    .settings-form {
      display: grid;
      gap: 12px;
      max-width: 420px;
    }
    .settings-field {
      display: grid;
      gap: 6px;
    }
    .settings-field label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }
    .settings-field input {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: rgba(8, 11, 16, .5);
      color: var(--text);
      padding: 10px 12px;
      font: inherit;
    }
    .settings-actions { display: flex; gap: 8px; align-items: center; }
    .settings-status { min-height: 18px; color: var(--muted); font-size: 12px; }
    .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    button {
      cursor: pointer; border: 1px solid var(--border); color: var(--text);
      background: #172231; padding: 8px 11px; border-radius: 10px;
    }
    button:hover { border-color: var(--blue); }
    button.active { border-color: var(--amber); color: var(--amber); background: rgba(240, 185, 11, .12); }
    .runtime-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 14px; align-items: stretch; }
    .runtime-grid > .panel { height: 245px; min-height: 0; overflow: hidden; }
    .log-panel { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
    .runtime-body { padding: 14px 16px; }
    .status-lines { display: grid; gap: 8px; }
    .status-line {
      display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 10px;
      align-items: center; font-size: 13px;
    }
    .status-key { color: var(--muted); }
    .status-value { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .log-box {
      flex: 1 1 auto; min-height: 0; overflow: auto; padding: 10px 14px;
      background: rgba(3, 7, 12, .58);
      font: 12px/1.45 "Cascadia Mono", "Consolas", monospace;
    }
    .log-line {
      display: grid; grid-template-columns: 76px 56px minmax(150px, 190px) minmax(0, 1fr); gap: 12px;
      padding: 3px 0; border-bottom: 1px solid rgba(34, 48, 65, .38);
    }
    .log-time, .log-file { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .log-msg { white-space: pre-wrap; word-break: break-word; }
    .level-error, .level-critical { color: var(--red); }
    .level-warning { color: var(--amber); }
    .level-info { color: var(--blue); }
    @media (max-width: 1050px) {
      .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .two-col { grid-template-columns: 1fr; }
      .stats-grid { grid-template-columns: 1fr; }
      .monitor-grid { grid-template-columns: 1fr; }
      .runtime-grid { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
    }
    @media (max-width: 620px) {
      .wrap { padding: 14px; }
      .cards { grid-template-columns: 1fr; }
      th, td { padding: 9px 10px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>Trading Bot Dashboard</h1>
        <div class="sub">Theo dõi lệnh mở, PnL thả nổi, PnL ngày và lịch sử lệnh.</div>
      </div>
      <div class="toolbar">
        <span class="pill" id="last-updated">Đang tải...</span>
        <button type="button" id="hard-trade-btn"><span id="hard-trade-text">Hard Trade OFF</span> <span class="help-dot" id="hard-trade-help" tabindex="0" role="img" aria-label="Cơ chế Hard Trade" data-tip="Hard Trade bật sẽ siết setup chặt hơn.&#10;Ưu tiên M30, xác nhận M15.&#10;M5 chỉ vào khi WR đủ cao.&#10;Mỗi lệnh tối đa 0.03 lot.&#10;Tổng tối đa 7 lệnh toàn hệ thống.&#10;Cuối tuần chỉ BTC được vào lệnh mới.&#10;Không vào Fast M1.">?</span></button>
        <span class="mode-label normal" id="recovery-mode-label"><span id="recovery-mode-text">Recovery: Normal</span><span class="help-dot" id="recovery-mode-help" tabindex="0" role="img" aria-label="Cơ chế Recovery" data-tip="Chỉ xét basket đã đóng gần nhất.&#10;Nếu basket đó lỗ và có dưới 5 lệnh thì vào Soft.&#10;Nếu có 5-6 lệnh thì vào Hard.&#10;Nếu có từ 7 lệnh trở lên thì xét mức đã gỡ lỗ để về Normal / Soft / Hard.&#10;Soft: setup mới cần WR >= 72%.&#10;Hard: setup mới cần WR >= 75%.&#10;Ví dụ: basket lỗ -7u, mới gỡ +3.5u -> Soft.&#10;Basket lỗ -7u, mới gỡ +3u và vẫn còn 5-6 lệnh -> Hard.&#10;Gỡ đủ lỗ hoặc hơn -> Normal.">?</span></span>
        <button type="button" id="forex-mode-btn"><span id="forex-mode-text">Forex OFF</span> <span class="help-dot" id="forex-mode-help" tabindex="0" role="img" aria-label="Cơ chế Forex mode" data-tip="Forex mode là công tắc riêng cho EURUSD, GBPUSD, USDJPY.&#10;Tắt: chặn lệnh forex mới, lệnh đang mở vẫn được chăm sóc.&#10;Bật: forex dùng chung trần 7 lệnh toàn hệ thống.&#10;Cuối tuần forex không vào lệnh mới.&#10;Basket win/loss của forex chỉ đóng nhóm forex.&#10;BTC và GOLD vẫn chạy theo basket riêng.">?</span></button>
        <button type="button" id="target-btn">Chỉnh target</button>
        <button type="button" id="refresh-btn">Refresh</button>
      </div>
    </header>

    <section class="panel improvement-panel top">
      <div class="panel-head">
        <div>
          <div class="panel-title">Đánh giá cải thiện của bot</div>
          <div class="panel-meta">
            <span id="improvement-meta">--</span>
            <span class="help-dot" id="improvement-help" tabindex="0" role="img" aria-label="Cơ chế cập nhật dữ liệu đánh giá" title="Cơ chế cập nhật dữ liệu đánh giá" data-tip="">?</span>
          </div>
        </div>
        <div class="improvement-range-tabs">
          <button type="button" class="improvement-range-tab active" data-improvement-range="today">Hôm nay</button>
          <button type="button" class="improvement-range-tab" data-improvement-range="yesterday">Hôm qua</button>
          <button type="button" class="improvement-range-tab" data-improvement-range="week">Tuần</button>
          <button type="button" class="improvement-range-tab" data-improvement-range="month">Tháng</button>
          <button type="button" class="improvement-range-tab improvement-compare-btn" id="improvement-compare-btn">So sánh</button>
        </div>
      </div>
      <div class="improvement-body" id="improvement-body">
        <div class="empty">Đang tải đánh giá...</div>
      </div>
    </section>

    <section class="grid stats-grid learning-stats-section">
      <div class="panel stats-panel learning-panel">
        <div class="panel-head">
          <div class="panel-title">Learning watchlist</div>
          <div class="panel-meta" id="learning-watch-meta">--</div>
        </div>
        <div class="scroll">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Nhóm</th><th>Action</th><th class="num">Lệnh</th><th class="num">WR</th><th class="num">PF</th><th class="num">PnL</th><th>Lý do</th>
              </tr>
            </thead>
            <tbody id="learning-watch-body"></tbody>
          </table>
        </div>
      </div>

      <div class="panel stats-panel learning-panel">
        <div class="panel-head">
          <div class="panel-title">Setup / Phiên tốt-xấu</div>
          <div class="panel-meta" id="learning-edge-meta">--</div>
        </div>
        <div class="scroll">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Loại</th><th>Nhóm</th><th class="num">Lệnh</th><th class="num">WR</th><th class="num">PnL</th><th class="num">Avg adverse</th>
              </tr>
            </thead>
            <tbody id="learning-edge-body"></tbody>
          </table>
        </div>
      </div>

      <div class="panel stats-panel">
        <div class="panel-head">
          <div class="panel-title">Quản lý lệnh</div>
          <div class="panel-meta" id="learning-management-meta">--</div>
        </div>
        <div class="scroll">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Cơ chế</th><th class="num">Lệnh</th><th class="num">WR</th><th class="num">PnL</th><th class="num">PF</th><th class="num">Avg favorable</th>
              </tr>
            </thead>
            <tbody id="learning-management-body"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="grid cards">
      <div class="card">
        <div class="label">Bot</div>
        <div class="value" id="bot-state">--</div>
        <div class="hint" id="bot-reason">--</div>
      </div>
      <div class="card">
        <div class="label">Lệnh đang mở</div>
        <div class="value" id="open-count">0</div>
        <div class="hint" id="open-lots">0 lot</div>
        <div class="card-actions"><button type="button" id="position-limit-btn">Điều chỉnh</button></div>
      </div>
      <div class="card">
        <div class="label">PnL thả nổi</div>
        <div class="value" id="floating-pnl">$0.00</div>
        <div class="hint">Tổng PnL các vị thế mở</div>
      </div>
      <div class="card">
        <div class="label">Vốn gốc</div>
        <div class="value" id="account-balance">$0.00</div>
        <div class="hint" id="account-detail">Không tính PnL thả nổi</div>
      </div>
      <div class="card">
        <div class="label-row">
          <div class="label">PnL ngày</div>
          <span class="help-dot" tabindex="0" role="img" aria-label="Cách tính PnL ngày" title="Cách tính PnL ngày" data-tip="PnL ngày = PnL đã chốt + PnL thả nổi. PnL đã chốt = balance hiện tại - vốn đầu ngày hoặc vốn sau lần reset dữ liệu gần nhất. PnL thả nổi = equity - balance, tức PnL các lệnh đang mở.">?</span>
        </div>
        <div class="value" id="daily-pnl">$0.00</div>
        <div class="hint" id="daily-detail">Realized + floating</div>
      </div>
      <div class="card">
        <div class="label">Target / Loss</div>
        <div class="value" id="target-loss-value"><span class="positive">+15</span> / <span class="negative">-100</span></div>
        <div class="hint" id="quality-rule">Fast WR = 70%</div>
        <div class="hint">USD trong ngày</div>
      </div>
    </section>

    <section class="grid basket-row">
      <div class="card">
        <div class="label">Basket Win</div>
        <div class="value" id="basket-win-value"><span class="positive">+5</span></div>
        <div class="hint" id="basket-win-detail">Thu?ng: FIXED_USD · $5.00 · Fast-only: $2.00 fast-only</div>
        <div class="card-actions"><button type="button" id="basket-win-btn">Setup</button></div>
      </div>
      <div class="card">
        <div class="label">Basket Loss</div>
        <div class="value" id="basket-loss-value"><span class="negative">-20</span></div>
        <div class="hint" id="basket-loss-detail">Cắt lỗ cho 1 nhóm lệnh</div>
        <div class="card-actions"><button type="button" id="basket-loss-btn">Setup</button></div>
      </div>
    </section>

    <section class="grid runtime-grid">
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Bot runtime</div>
          <div class="panel-meta" id="runtime-meta">--</div>
        </div>
        <div class="runtime-body status-lines">
          <div class="status-line"><span class="status-key">API</span><span class="status-value" id="rt-api">--</span></div>
          <div class="status-line"><span class="status-key">Worker</span><span class="status-value" id="rt-worker">--</span></div>
          <div class="status-line"><span class="status-key">MT5</span><span class="status-value" id="rt-mt5">--</span></div>
          <div class="status-line"><span class="status-key">Mode</span><span class="status-value" id="rt-mode">--</span></div>
          <div class="status-line"><span class="status-key">Symbols</span><span class="status-value" id="rt-symbols">--</span></div>
        </div>
      </div>

      <div class="panel log-panel">
        <div class="panel-head">
          <div class="panel-title">System log</div>
          <div class="panel-meta" id="logs-meta">--</div>
        </div>
        <div class="log-box" id="system-log-body">
          <div class="empty">Dang tai log...</div>
        </div>
      </div>

      <div class="panel signal-panel">
        <div class="panel-head">
          <div class="panel-title">Tín hiệu mới nhất</div>
          <div class="panel-meta" id="signal-time">--</div>
        </div>
        <div class="signal-content">
          <div class="grid signal-grid">
            <div class="signal-main">
              <div><div class="label">Symbol</div><div class="signal-value" id="sig-symbol">--</div></div>
              <div><div class="label">Decision</div><div class="signal-value" id="sig-decision">--</div></div>
              <div><div class="label">Side / Trend</div><div class="signal-value" id="sig-side">--</div></div>
            </div>
            <div class="signal-reason">
              <div><div class="label">Score</div><div class="signal-value" id="sig-score">--</div></div>
              <div class="label">Lý do</div>
              <div class="hint" id="sig-reason" style="font-size:14px;">--</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="grid monitor-grid">
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Lệnh đang mở</div>
          <div class="panel-meta" id="positions-meta">--</div>
        </div>
        <div class="scroll positions-scroll">
          <table class="positions-table">
            <colgroup>
              <col style="width: 7%">
              <col style="width: 9%">
              <col style="width: 7%">
              <col style="width: 6%">
              <col style="width: 9%">
              <col style="width: 6%">
              <col style="width: 5%">
              <col style="width: 8%">
              <col style="width: 8%">
              <col style="width: 13%">
              <col style="width: 13%">
              <col style="width: 9%">
            </colgroup>
            <thead>
              <tr>
                <th>Ticket</th><th>Loại</th><th class="num">Mở lúc</th><th class="num">WR</th><th>Cặp</th><th>Side</th><th class="num">Lot</th>
                <th class="num">Entry</th><th class="num">Giá</th><th class="num">SL</th><th class="num">TP</th><th class="num">PnL</th>
              </tr>
            </thead>
            <tbody id="positions-body"></tbody>
          </table>
          <div class="empty" id="positions-empty">Không có lệnh đang mở.</div>
        </div>
      </div>
    </section>

    <section class="grid stats-grid" style="margin-top:14px;">
      <div class="panel stats-panel">
        <div class="panel-head">
          <div class="panel-title">Hiệu suất theo loại lệnh</div>
          <div class="panel-meta" id="type-stats-meta">--</div>
        </div>
        <div class="scroll">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Loại</th><th class="num">Đã đóng</th><th class="num">Thắng</th><th class="num">Thua</th>
                <th class="num">Win rate</th><th class="num">Net PnL</th><th class="num">Avg Win</th><th class="num">Avg Loss</th>
              </tr>
            </thead>
            <tbody id="type-stats-body"></tbody>
          </table>
        </div>
      </div>

      <div class="panel stats-panel">
        <div class="panel-head">
          <div class="panel-title">Hiệu suất theo cặp</div>
          <div class="panel-meta" id="symbol-stats-meta">--</div>
        </div>
        <div class="scroll">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Cặp</th><th class="num">Đã đóng</th><th class="num">Thắng</th><th class="num">Thua</th>
                <th class="num">Win rate</th><th class="num">Net PnL</th><th class="num">Avg Win</th><th class="num">Avg Loss</th>
              </tr>
            </thead>
            <tbody id="symbol-stats-body"></tbody>
          </table>
        </div>
      </div>

      <div class="panel stats-panel">
        <div class="panel-head">
          <div class="panel-title">Hiệu suất theo ngày</div>
          <div class="panel-meta" id="day-stats-meta">--</div>
        </div>
        <div class="scroll daily-stats-scroll">
          <table class="stats-table">
            <thead>
              <tr>
                <th>Ngày</th><th class="num">Đã đóng</th><th class="num">Thắng</th><th class="num">Thua</th>
                <th class="num">Win rate</th><th class="num">Net PnL</th>
              </tr>
            </thead>
            <tbody id="day-stats-body"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:14px;">
      <div class="panel-head">
        <div class="panel-title">Lịch sử lệnh gần đây</div>
        <div class="panel-meta" id="trades-meta">--</div>
      </div>
      <div class="scroll">
        <table class="forex-history-table">
          <thead>
            <tr>
              <th>ID</th><th>Ticket</th><th>Loại</th><th class="num">WR</th><th>Cặp</th><th>Side</th><th>State</th><th>Lý do <span class="help-dot" tabindex="0" role="img" aria-label="Lý do đóng lệnh" title="Lý do đóng lệnh" data-tip="SL: chạm stop loss.&#10;TP: chạm take profit.&#10;BW: basket win, bot đóng khi đạt ngưỡng lời basket.&#10;BL: basket loss, bot đóng khi chạm ngưỡng lỗ basket.&#10;BVL: Bảo Vệ Lãi, bot nhận thấy đảo chiều và đóng lệnh để bảo vệ lãi.&#10;SLD: chạm SL dương đã được bot dời lên.">?</span></th><th class="num">Lot</th>
              <th class="num">Entry</th><th class="num">SL</th><th class="num">TP</th><th class="num">PnL</th><th>Mở lúc</th><th>Đóng lúc</th>
            </tr>
          </thead>
          <tbody id="trades-body"></tbody>
        </table>
      </div>
    </section>
  </div>

  <div class="modal-overlay" id="forex-stats-modal" aria-hidden="true">
    <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="forex-modal-title">
      <div class="modal-head">
        <div>
          <div class="panel-title" id="forex-modal-title">Tiền tệ</div>
          <div class="panel-meta" id="forex-modal-meta">--</div>
        </div>
        <button type="button" class="modal-close" id="forex-modal-close" aria-label="Đóng">×</button>
      </div>
      <div class="modal-body">
        <div class="modal-section-title">Hiệu suất từng cặp</div>
        <table class="stats-table modal-stats-table">
          <thead>
            <tr>
              <th>Cặp</th><th class="num">Đã đóng</th><th class="num">Thắng</th><th class="num">Thua</th>
              <th class="num">Win rate</th><th class="num">Net PnL</th><th class="num">Avg Win</th><th class="num">Avg Loss</th>
            </tr>
          </thead>
          <tbody id="forex-modal-stats-body"></tbody>
        </table>
        <div class="modal-section-title">Lịch sử giao dịch tiền tệ</div>
        <table class="forex-history-table">
          <thead>
            <tr>
              <th>ID</th><th>Ticket</th><th>Loại</th><th class="num">WR</th><th>Cặp</th><th>Side</th><th>State</th><th>Lý do <span class="help-dot" tabindex="0" role="img" aria-label="Lý do đóng lệnh" title="Lý do đóng lệnh" data-tip="SL: chạm stop loss.&#10;TP: chạm take profit.&#10;BW: basket win, bot đóng khi đạt ngưỡng lời basket.&#10;BL: basket loss, bot đóng khi chạm ngưỡng lỗ basket.&#10;BVL: Bảo Vệ Lãi, bot nhận thấy đảo chiều và đóng lệnh để bảo vệ lãi.&#10;SLD: chạm SL dương đã được bot dời lên.">?</span></th><th class="num">Lot</th>
              <th class="num">Entry</th><th class="num">SL</th><th class="num">TP</th><th class="num">PnL</th><th>Mở lúc</th><th>Đóng lúc</th>
            </tr>
          </thead>
          <tbody id="forex-modal-trades-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="position-limit-modal" aria-hidden="true">
    <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="position-limit-title" style="width:min(520px, 94vw);">
      <div class="modal-head">
        <div>
          <div class="panel-title" id="position-limit-title">Điều chỉnh lệnh đang mở</div>
          <div class="panel-meta">Áp dụng chung cho BUY và SELL</div>
        </div>
        <button type="button" class="modal-close" id="position-limit-close" aria-label="Đóng">×</button>
      </div>
      <div class="modal-body">
        <div class="settings-form">
          <div class="settings-field">
            <label for="position-limit-input">Tổng số lệnh tối đa</label>
            <input id="position-limit-input" type="number" min="1" step="1" inputmode="numeric" />
          </div>
          <div class="settings-status" id="position-limit-status">--</div>
          <div class="settings-actions">
            <button type="button" id="position-limit-save">Lưu</button>
            <button type="button" id="position-limit-cancel">Hủy</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="daily-risk-modal" aria-hidden="true">
    <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="daily-risk-title" style="width:min(520px, 94vw);">
      <div class="modal-head">
        <div>
          <div class="panel-title" id="daily-risk-title">Chỉnh target ngày</div>
          <div class="panel-meta">Target lời và mức lỗ tối đa theo USD</div>
        </div>
        <button type="button" class="modal-close" id="daily-risk-close" aria-label="Đóng">×</button>
      </div>
      <div class="modal-body">
        <div class="settings-form">
          <div class="settings-field">
            <label for="daily-target-input">Target lời/ngày USD</label>
            <input id="daily-target-input" type="number" min="0.01" step="0.01" inputmode="decimal" />
          </div>
          <div class="settings-field">
            <label for="daily-loss-input">Lỗ tối đa/ngày USD</label>
            <input id="daily-loss-input" type="number" min="0.01" step="0.01" inputmode="decimal" />
          </div>
          <div class="settings-status" id="daily-risk-status">--</div>
          <div class="settings-actions">
            <button type="button" id="daily-risk-save">Lưu</button>
            <button type="button" id="daily-risk-cancel">Hủy</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="help-tooltip" id="help-tooltip" role="tooltip" aria-hidden="true"></div>

  <div class="modal-overlay" id="improvement-compare-modal" aria-hidden="true">
    <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="improvement-compare-title">
      <div class="modal-head">
        <div>
          <div class="panel-title" id="improvement-compare-title">Bot có khôn hơn chưa?</div>
          <div class="panel-meta" id="improvement-compare-meta">--</div>
        </div>
        <button type="button" class="modal-close" id="improvement-compare-close" aria-label="Đóng">×</button>
      </div>
      <div class="modal-body">
        <div class="compare-tabs">
          <button type="button" class="compare-tab active" data-compare-range="day">Hôm nay</button>
          <button type="button" class="compare-tab" data-compare-range="week">7 ngày</button>
          <button type="button" class="compare-tab" data-compare-range="month">30 ngày</button>
          <button type="button" class="compare-tab" data-compare-range="quarter">90 ngày</button>
        </div>
        <p class="compare-note" id="improvement-compare-note">So sánh theo ngày giao dịch 07:00 sáng giờ Việt Nam.</p>
        <div class="modal-section-title">Tổng quan</div>
        <table class="stats-table compare-table">
          <thead><tr><th>Chỉ số</th><th id="compare-prev-head">Kỳ trước</th><th id="compare-current-head">Kỳ này</th><th>Đánh giá</th></tr></thead>
          <tbody id="improvement-compare-summary"></tbody>
        </table>
        <div class="modal-section-title">Theo cặp</div>
        <table class="stats-table compare-table">
          <thead><tr><th>Cặp</th><th>Kỳ trước</th><th>Kỳ này</th><th>Nhận xét</th></tr></thead>
          <tbody id="improvement-compare-symbols"></tbody>
        </table>
        <div class="modal-section-title">Lý do đóng</div>
        <table class="stats-table compare-table">
          <thead><tr><th>Lý do</th><th>Kỳ trước</th><th>Kỳ này</th><th>Nhận xét</th></tr></thead>
          <tbody id="improvement-compare-reasons"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const fmtMoney = (value) => {
      const n = Number(value || 0);
      return `${n < 0 ? "-" : ""}$${Math.abs(n).toFixed(2)}`;
    };
    const fmtNum = (value, digits = 2) => value === null || value === undefined || value === "" ? "--" : Number(value).toFixed(digits);
    const priceCell = (value, digits = 2, extraClass = "") => `<span class="price-cell ${extraClass}">${fmtNum(value, digits)}</span>`;
    const moneyCell = (value) => `<span class="price-cell ${clsPnl(value)}">${fmtMoney(value)}</span>`;
    const fmtPriceWithPnl = (price, pnl) => {
      if (price === null || price === undefined || price === "" || pnl === null || pnl === undefined || !Number.isFinite(Number(pnl))) {
        return priceCell(price);
      }
      const n = Number(pnl);
      const sign = n >= 0 ? "+" : "";
      const klass = n >= 0 ? "positive" : "negative";
      return `<span class="price-pnl"><span>${fmtNum(price)}</span><small class="${klass}">(${sign}${n.toFixed(2)}u)</small></span>`;
    };
    const fmtTime = (value) => {
      if (!value) return "--";
      const date = new Date(String(value).replace(" ", "T") + (String(value).includes("Z") ? "" : "Z"));
      return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("vi-VN");
    };
    const fmtShortDateTime = (value) => {
      if (!value) return "--";
      const full = fmtTime(value);
      const date = parseTime(value);
      if (!date) return `<span class="time-short" title="${escapeHtml(full)}">${escapeHtml(String(value).slice(0, 8))}...</span>`;
      const hh = String(date.getHours()).padStart(2, "0");
      const mm = String(date.getMinutes()).padStart(2, "0");
      const ss = String(date.getSeconds()).padStart(2, "0");
      const short = `${hh}:${mm}:${ss} ${date.getDate()}/${date.getMonth() + 1}/...`;
      return `<span class="time-short" title="${escapeHtml(full)}">${short}</span>`;
    };
    const parseTime = (value) => {
      if (!value) return null;
      const text = String(value);
      const hasZone = text.includes("Z") || /[+-]\d\d:\d\d$/.test(text);
      const date = new Date(text.replace(" ", "T") + (hasZone ? "" : "Z"));
      return Number.isNaN(date.getTime()) ? null : date;
    };
    const fmtCompareDate = (date) => `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")} ${date.getDate()}/${date.getMonth() + 1}`;
    const symbolBase = (symbol) => String(symbol || "--").replace(/[^A-Za-z]/g, "").toUpperCase() || String(symbol || "--").toUpperCase();
    const fmtOpenTime = (value) => {
      const date = parseTime(value);
      if (!date) return "--";
      return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    };
    const clsPnl = (value) => Number(value || 0) >= 0 ? "positive" : "negative";
    const setText = (id, value) => { document.getElementById(id).textContent = value; };
    const setHtml = (id, value) => { document.getElementById(id).innerHTML = value; };
    const setMoney = (id, value) => {
      const el = document.getElementById(id);
      el.textContent = fmtMoney(value);
      el.className = `value ${clsPnl(value)}`;
    };
    const setPlainMoney = (id, value) => {
      const el = document.getElementById(id);
      el.textContent = fmtMoney(value);
      el.className = "value blue";
    };
    const setRichValue = (id, html) => { document.getElementById(id).innerHTML = html; };
    let currentDailyTargetUsd = null;
    let currentDailyLossUsd = null;
    let currentBasketStopLoss = null;
    let currentBasketTakeProfit = null;
    let currentFastBasketTakeProfit = null;
    let currentBasketTakeProfitMode = "FIXED_USD";
    let currentBasketTargetFixedUsd = 5;
    let currentBasketFastTargetFixedUsd = 2;
    let currentBasketTargetRMultiple = 1.5;
    let currentBasketTargetEquityPercent = 1.0;
    let currentBasketMode = "FIXED_USD";
    let currentBasketFixedUsd = 20;
    let currentBasketBalancedRatio = 0.2;
    let currentBasketBalancedFloor = 3;
    let currentHardTradeEnabled = false;
    let currentForexTradingEnabled = false;
    let currentForexTradingSymbols = ["EURUSD", "GBPUSD", "USDJPY"];
    let currentGlobalOpenPositions = 7;
    let currentMaxBuyPositions = 1;
    let currentMaxSellPositions = 1;
    const CORE_REFRESH_MS = 1000;
    const SLOW_REFRESH_MS = 10000;
    const LOG_REFRESH_MS = 15000;
    const FETCH_TIMEOUT_MS = 2500;
    let lastSlowRefreshAt = 0;
    let lastLogRefreshAt = 0;
    let dashboardLoading = false;
    let slowDataLoading = false;
    let slowDataVersion = 0;
    let renderedSlowDataVersion = -1;
    let cachedTrades = [];
    let cachedPositions = [];
    let cachedSignal = null;
    let cachedSpecs = {};
    let cachedConfig = null;
    let cachedLearning = null;
    let activeCompareRange = "day";
    let activeImprovementRange = "today";
    const FOREX_SYMBOLS = new Set(["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]);
    const badge = (text, extra = "") => `<span class="badge ${extra}">${text || "--"}</span>`;
    const forexIconText = (upper) => {
      const aliases = {
        EURUSD: "EU",
        GBPUSD: "GU",
        USDJPY: "UJ",
        AUDUSD: "AU",
        USDCAD: "UC",
        USDCHF: "UF",
        NZDUSD: "NU",
      };
      return aliases[upper.replace(/[^A-Z]/g, "").slice(0, 6)] || upper.replace(/[^A-Z]/g, "").slice(0, 2) || "FX";
    };
    const forexLogoClass = (upper) => {
      if (upper.includes("JPY")) return "forex jpy";
      if (upper.includes("CHF")) return "forex chf";
      return "forex";
    };
    const symbolCell = (symbol) => {
      const raw = String(symbol || "--");
      const upper = raw.toUpperCase();
      if (upper.includes("BTC")) {
        return `<span class="symbol-cell"><span class="symbol-logo btc">?</span><span>${raw}</span></span>`;
      }
      if (upper.includes("GOLD") || upper.includes("XAU")) {
        return `<span class="symbol-cell"><span class="symbol-logo gold">Au</span><span>${raw}</span></span>`;
      }
      if (/^[A-Z]{6}/.test(upper)) {
        return `<span class="symbol-cell"><span class="symbol-logo ${forexLogoClass(upper)}">${forexIconText(upper)}</span><span>${raw}</span></span>`;
      }
      return `<span class="symbol-cell"><span class="symbol-logo generic">FX</span><span>${raw}</span></span>`;
    };
    const typeFromKey = (key) => {
      if (!key) return "--";
      if (key.includes("_M1_")) return "Fast M1";
      if (key.includes("_M5_")) return "Setup M5";
      if (key.includes("_M15_")) return "Setup M15";
      return "--";
    };
    const timeframeFromKey = (key) => {
      if (!key) return "--";
      if (key.includes("_M1_")) return "M1";
      if (key.includes("_M5_")) return "M5";
      if (key.includes("_M15_")) return "M15";
      if (key.includes("_M30_")) return "M30";
      return "--";
    };
    const tradePnl = (trade) => {
      const realized = Number(trade.realized_profit ?? 0);
      const floating = Number(trade.floating_profit ?? 0);
      if (isClosedTrade(trade) && Math.abs(realized) < 1e-9 && Math.abs(floating) > 1e-9) return floating;
      return Number(trade.realized_profit ?? trade.floating_profit ?? 0);
    };
    const isClosedTrade = (trade) => Boolean(trade.closed_at) || String(trade.state || "").toUpperCase() === "CLOSED";
    const closeReasonCell = (trade) => {
      const state = String(trade.state || "").toUpperCase();
      if (!trade.closed_at && state !== "CLOSED") return "--";
      const reason = String(trade.close_reason || "").toUpperCase();
      const pnl = tradePnl(trade);
      const side = String(trade.side || "").toUpperCase();
      const entry = Number(trade.entry_price);
      const stop = Number(trade.stop_loss);
      const hasPositiveStop =
        Number.isFinite(entry) &&
        Number.isFinite(stop) &&
        ((side === "BUY" && stop > entry) || (side === "SELL" && stop < entry));
      let code = reason || "CLOSED";
      let label = code;
      if (reason === "TAKE_PROFIT") label = "BW";
      else if (reason === "STOP_LOSS") label = "BL";
      else if (reason === "PROFIT_PROTECTION") label = "BVL";
      else if (reason === "BROKER_SIDE_EXIT") label = pnl >= 0 ? (hasPositiveStop ? "SLD" : "TP") : "SL";
      else if (reason.includes("TAKE_PROFIT")) label = "BW";
      else if (reason.includes("STOP_LOSS")) label = "BL";
      else if (pnl > 0) label = "TP";
      else if (pnl < 0) label = "SL";
      const cls = ["TP", "BW", "SLD", "BVL", "SL", "BL"].includes(label) ? label.toLowerCase() : "";
      return `<span class="close-reason ${cls}" title="${code}">${label}</span>`;
    };
    const dayKey = (value) => {
      if (!value) return "--";
      return String(value).replace("T", " ").slice(0, 10);
    };
    const buildStats = (items) => {
      const pnls = items.map(tradePnl);
      const wins = pnls.filter(v => v > 0);
      const losses = pnls.filter(v => v < 0);
      const net = pnls.reduce((sum, v) => sum + v, 0);
      return {
        total: items.length,
        wins: wins.length,
        losses: losses.length,
        winRate: items.length ? wins.length / items.length * 100 : 0,
        net,
        avgWin: wins.length ? wins.reduce((sum, v) => sum + v, 0) / wins.length : 0,
        avgLoss: losses.length ? losses.reduce((sum, v) => sum + v, 0) / losses.length : 0,
      };
    };
    const average = (values) => values.length ? values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length : 0;
    const tradingDayStart = (date) => {
      const start = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 7, 0, 0, 0);
      if (date < start) start.setDate(start.getDate() - 1);
      return start;
    };
    const addDays = (date, days) => new Date(date.getTime() + days * 86400000);
    const improvementWindow = (range, offset = 0) => {
      const now = new Date();
      const today = tradingDayStart(now);
      if (range === "yesterday") {
        const start = addDays(today, -1 + offset);
        return { start, end: addDays(start, 1), label: offset ? "Hôm kia" : "Hôm qua" };
      }
      if (range === "week") {
        const currentStart = addDays(today, -6);
        const currentEnd = now;
        const start = offset ? addDays(currentStart, offset * 7) : currentStart;
        const end = offset ? addDays(currentEnd, offset * 7) : currentEnd;
        return { start, end, label: offset ? "7 ngày tru?c" : "7 ngày" };
      }
      if (range === "month") {
        const currentStart = addDays(today, -29);
        const currentEnd = now;
        const start = offset ? addDays(currentStart, offset * 30) : currentStart;
        const end = offset ? addDays(currentEnd, offset * 30) : currentEnd;
        return { start, end, label: offset ? "30 ngày trước" : "30 ngày" };
      }
      const start = addDays(today, offset);
      return { start, end: offset ? addDays(start, 1) : now, label: offset ? "Hôm qua" : "Hôm nay" };
    };
    const fmtWindowDate = (date) => `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")} ngày ${date.getDate()}/${date.getMonth() + 1}`;
    const fmtWindowEnd = (date) => `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")} ngày ${date.getDate()}/${date.getMonth() + 1}`;
    const setImprovementHelp = (window) => {
      const help = document.getElementById("improvement-help");
      if (!help) return;
      const selected = activeImprovementRange === "today"
        ? `Hôm nay = từ ${fmtWindowDate(window.start)} đến hiện tại.`
        : activeImprovementRange === "yesterday"
        ? `Hôm qua = từ ${fmtWindowDate(window.start)} đến ${fmtWindowEnd(new Date(window.end.getTime() - 60000))}.`
        : activeImprovementRange === "week"
        ? `Tuần = từ ${fmtWindowDate(window.start)} đến hiện tại, gồm 7 ngày giao dịch gần nhất.`
        : `Tháng = từ ${fmtWindowDate(window.start)} đến hiện tại, gồm 30 ngày giao dịch gần nhất.`;
      help.dataset.tip = [
        "• Các chỉ số dùng mốc ngày giao dịch 07:00 sáng giờ Việt Nam.",
        `  • ${selected}`,
        "  • Hôm nay đổi sang ngày mới lúc 07:00 sáng.",
        "  • Hôm qua là phiên giao dịch liền trước, từ 07:00 đến 06:59.",
        "  • Tuần/Tháng cập nhật liên tục theo thời điểm hiện tại, không đợi hết tuần/tháng lịch.",
        "  • Lệnh mở/floating cập nhật khoảng mỗi 1 giây.",
        "  • Trade history, win rate, telemetry và chỉ số tự học cập nhật khoảng mỗi 10 giây.",
      ].join("\\n");
    };
    const tradeInWindow = (trade, window) => {
      const dt = parseTime(trade.closed_at || trade.opened_at);
      return dt && dt >= window.start && dt < window.end;
    };
    const delta = (current, previous, higherIsBetter = true, suffix = "") => {
      if (!Number.isFinite(Number(current)) || !Number.isFinite(Number(previous))) return "";
      const diff = Number(current) - Number(previous);
      if (Math.abs(diff) < 1e-9) return `<span class="delta">? 0${suffix}</span>`;
      const better = higherIsBetter ? diff > 0 : diff < 0;
      return `<span class="delta ${better ? "positive" : "negative"}">${diff > 0 ? "?" : "?"} ${Math.abs(diff).toFixed(2)}${suffix}</span>`;
    };
    const fact = (label, value, klass = "", important = false) => `<div><span>${important ? '<b class="watch">*</b> ' : ""}${label}</span><strong class="${klass}">${value}</strong></div>`;
    const improvementCard = (title, mainLabel, mainValue, mainClass, facts, deltaHtml = "", important = true) => `
      <div class="improvement-item">
        <h3>${title}</h3>
        <div class="label">${important ? '<b class="watch">*</b> ' : ""}${mainLabel}</div>
        <div class="metric-row"><div class="metric ${mainClass || ""}">${mainValue}</div>${deltaHtml}</div>
        <div class="improvement-facts">${facts.join("")}</div>
      </div>`;
    const improvementData = (trades, positions, config, range = activeImprovementRange, previous = false) => {
      const window = improvementWindow(range, previous ? -1 : 0);
      const windowTrades = trades.filter(t => tradeInWindow(t, window));
      const closed = windowTrades.filter(isClosedTrade);
      const recentClosed = closed.slice(0, 30);
      const withWr = closed.filter(t => Number.isFinite(Number(t.estimated_win_rate)));
      const riskReady = closed.filter(t => Number.isFinite(Number(t.initial_risk_amount)) && Number(t.initial_risk_amount) > 0);
      const painful = riskReady.filter(t => Number(t.max_adverse_r || 0) >= Number(config?.adaptive_learning?.drawdown_pain_r || 0.8));
      const addons = closed.filter(t => Number(t.entry_number || 1) >= 2);
      const addonStats = buildStats(addons);
      const recentStats = buildStats(recentClosed);
      const allStats = buildStats(closed);
      const avgWr = average(withWr.map(t => Number(t.estimated_win_rate)));
      const avgPain = average(riskReady.map(t => Number(t.max_adverse_r || 0)));
      const hard = config?.hard_trade || {};
      const learning = config?.adaptive_learning || {};
      return { window, windowTrades, closed, recentClosed, withWr, riskReady, painful, addons, addonStats, recentStats, allStats, avgWr, avgPain, hard, learning, openCount: positions.length };
    };
    const closedTradeInWindow = (trade, window) => {
      const dt = parseTime(trade.closed_at);
      return isClosedTrade(trade) && dt && dt >= window.start && dt < window.end;
    };
    const openedTradeInWindow = (trade, window) => {
      const dt = parseTime(trade.opened_at);
      return dt && dt >= window.start && dt < window.end;
    };
    const compareWindows = (range) => {
      const now = new Date();
      const today = tradingDayStart(now);
      if (range === "week") {
        const current = { start: addDays(today, -6), end: now, label: "7 ngày này" };
        const previous = { start: addDays(current.start, -7), end: addDays(current.end, -7), label: "7 ngày trước" };
        return { current, previous, note: "7 ngày này là 7 ngày giao dịch gần nhất tính từ mốc 07:00 đến hiện tại." };
      }
      if (range === "month") {
        const current = { start: addDays(today, -29), end: now, label: "30 ngày này" };
        const previous = { start: addDays(current.start, -30), end: addDays(current.end, -30), label: "30 ngày trước" };
        return { current, previous, note: "30 ngày này là 30 ngày giao dịch gần nhất tính từ mốc 07:00 đến hiện tại." };
      }
      if (range === "quarter") {
        const current = { start: addDays(today, -89), end: now, label: "90 ngày này" };
        const previous = { start: addDays(current.start, -90), end: addDays(current.end, -90), label: "90 ngày trước" };
        return { current, previous, note: "90 ngày này dùng toàn bộ khung dữ liệu học dài hơn đang giữ." };
      }
      const current = { start: today, end: now, label: "Hôm nay" };
      const previous = { start: addDays(today, -1), end: today, label: "Hôm qua" };
      return { current, previous, note: "Hôm nay tính từ 07:00 đến hiện tại; hôm qua tính từ 07:00 hôm qua đến 06:59 hôm nay." };
    };
    const comparisonData = (trades, range = activeCompareRange) => {
      const windows = compareWindows(range);
      const make = (window) => {
        const closed = trades.filter(t => closedTradeInWindow(t, window));
        const opened = trades.filter(t => openedTradeInWindow(t, window));
        const stats = buildStats(closed);
        const riskReady = closed.filter(t => Number.isFinite(Number(t.max_adverse_r)));
        const painful = riskReady.filter(t => Number(t.max_adverse_r || 0) >= Number(cachedConfig?.adaptive_learning?.drawdown_pain_r || 0.8));
        const reasons = groupBy(closed, t => t.close_reason || "UNKNOWN");
        const symbols = groupBy(closed, t => symbolBase(t.symbol || "--"));
        const brokerLosses = closed.filter(t => (t.close_reason || "") === "BROKER_SIDE_EXIT" && tradePnl(t) < 0);
        return {
          window,
          opened,
          closed,
          stats,
          riskReady,
          painful,
          avgPain: average(riskReady.map(t => Number(t.max_adverse_r || 0))),
          brokerLosses,
          brokerLossPnl: brokerLosses.reduce((sum, t) => sum + tradePnl(t), 0),
          reasons,
          symbols,
        };
      };
      return { current: make(windows.current), previous: make(windows.previous), windows };
    };
    const compareVerdict = (today, yesterday, higherIsBetter = true, suffix = "") => {
      const diff = Number(today || 0) - Number(yesterday || 0);
      const improved = higherIsBetter ? diff > 0 : diff < 0;
      const same = Math.abs(diff) < 1e-9;
      if (same) return `<span class="">Không đổi</span>`;
      const klass = improved ? "positive" : "negative";
      const sign = diff > 0 ? "+" : "";
      return `<span class="${klass}">${improved ? "Tốt hơn" : "Xấu hơn"} (${sign}${diff.toFixed(2)}${suffix})</span>`;
    };
    const compareRow = (label, yesterday, today, verdictHtml) => row([
      [label],
      [yesterday, "num"],
      [today, "num"],
      [verdictHtml],
    ]);
    const groupStatsLabel = (items) => {
      const stats = buildStats(items || []);
      return `${stats.total} lệnh · <span class="${clsPnl(stats.net)}">${fmtMoney(stats.net)}</span>`;
    };
    function renderImprovementCompareModal() {
      const data = comparisonData(cachedTrades);
      const y = data.previous;
      const t = data.current;
      setText("compare-prev-head", data.windows.previous.label);
      setText("compare-current-head", data.windows.current.label);
      setText("improvement-compare-note", `So sánh theo ngày giao dịch 07:00 sáng giờ Việt Nam. ${data.windows.note}`);
      const currentEnd = activeCompareRange === "day" ? "hiện tại" : fmtCompareDate(t.window.end);
      setText("improvement-compare-meta", `${data.windows.previous.label}: ${fmtCompareDate(y.window.start)} -> ${fmtCompareDate(y.window.end)} · ${data.windows.current.label}: ${fmtCompareDate(t.window.start)} -> ${currentEnd}`);
      document.getElementById("improvement-compare-summary").innerHTML = [
        compareRow("Lệnh mở mới", y.opened.length, t.opened.length, compareVerdict(t.opened.length, y.opened.length, false)),
        compareRow("Lệnh đã đóng", y.closed.length, t.closed.length, compareVerdict(t.closed.length, y.closed.length, true)),
        compareRow("Win rate", `${y.stats.winRate.toFixed(1)}%`, `${t.stats.winRate.toFixed(1)}%`, compareVerdict(t.stats.winRate, y.stats.winRate, true, "%")),
        compareRow("Realized PnL", `<span class="${clsPnl(y.stats.net)}">${fmtMoney(y.stats.net)}</span>`, `<span class="${clsPnl(t.stats.net)}">${fmtMoney(t.stats.net)}</span>`, compareVerdict(t.stats.net, y.stats.net, true)),
        compareRow("Avg win", fmtMoney(y.stats.avgWin), fmtMoney(t.stats.avgWin), compareVerdict(t.stats.avgWin, y.stats.avgWin, true)),
        compareRow("Avg loss", fmtMoney(y.stats.avgLoss), fmtMoney(t.stats.avgLoss), compareVerdict(t.stats.avgLoss, y.stats.avgLoss, true)),
        compareRow("Lệnh đau >=0.8R", y.painful.length, t.painful.length, compareVerdict(t.painful.length, y.painful.length, false)),
        compareRow("Avg max adverse", `${y.avgPain.toFixed(3)}R`, `${t.avgPain.toFixed(3)}R`, compareVerdict(t.avgPain, y.avgPain, false, "R")),
        compareRow("Lỗ broker-side", `<span class="${clsPnl(y.brokerLossPnl)}">${fmtMoney(y.brokerLossPnl)}</span>`, `<span class="${clsPnl(t.brokerLossPnl)}">${fmtMoney(t.brokerLossPnl)}</span>`, compareVerdict(t.brokerLossPnl, y.brokerLossPnl, true)),
      ].join("");
      const symbolKeys = Array.from(new Set([...y.symbols.keys(), ...t.symbols.keys()])).sort();
      document.getElementById("improvement-compare-symbols").innerHTML = symbolKeys.length
        ? symbolKeys.map(symbol => {
            const yItems = y.symbols.get(symbol) || [];
            const tItems = t.symbols.get(symbol) || [];
            const yNet = buildStats(yItems).net;
            const tNet = buildStats(tItems).net;
            return row([
              [symbolCell(symbol)],
              [groupStatsLabel(yItems), "num"],
              [groupStatsLabel(tItems), "num"],
              [compareVerdict(tNet, yNet, true)],
            ]);
          }).join("")
        : `<tr><td colspan="4" class="empty">Chưa có dữ liệu</td></tr>`;
      const reasonKeys = Array.from(new Set([...y.reasons.keys(), ...t.reasons.keys()])).sort();
      document.getElementById("improvement-compare-reasons").innerHTML = reasonKeys.length
        ? reasonKeys.map(reason => {
            const yItems = y.reasons.get(reason) || [];
            const tItems = t.reasons.get(reason) || [];
            const yNet = buildStats(yItems).net;
            const tNet = buildStats(tItems).net;
            const higherIsBetter = reason !== "BROKER_SIDE_EXIT" && reason !== "STOP_LOSS";
            return row([
              [reason],
              [groupStatsLabel(yItems), "num"],
              [groupStatsLabel(tItems), "num"],
              [compareVerdict(tNet, yNet, higherIsBetter)],
            ]);
          }).join("")
        : `<tr><td colspan="4" class="empty">Chưa có dữ liệu</td></tr>`;
    }
    function openImprovementCompareModal() {
      renderImprovementCompareModal();
      const modal = document.getElementById("improvement-compare-modal");
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
    }
    function closeImprovementCompareModal() {
      const modal = document.getElementById("improvement-compare-modal");
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }
    const renderImprovementPanel = (trades, positions, config) => {
      const data = improvementData(trades, positions, config);
      const prev = improvementData(trades, positions, config, activeImprovementRange, true);
      const hardOn = data.hard.enabled ? "ON" : "OFF";
      const learningOn = data.learning.enabled ? "ON" : "OFF";
      const body = document.getElementById("improvement-body");
      const metaParts = [
        data.window.label,
        `Hard ${hardOn}`,
        `Learning ${learningOn}`,
        `${data.closed.length} lệnh đóng`,
        `${data.riskReady.length} có risk telemetry`,
      ];
      setText("improvement-meta", metaParts.join(" · "));
      setImprovementHelp(data.window);
      body.innerHTML = `
        <div class="improvement-grid">
          ${improvementCard("Tổng quan", "Realized đã đóng", fmtMoney(data.allStats.net), clsPnl(data.allStats.net), [
            fact("Lệnh đang mở", `${data.openCount}/${Number(config?.position_control?.max_open_positions || currentGlobalOpenPositions)}`),
            fact("Hard Trade", hardOn),
            fact("Learning", learningOn),
          ], delta(data.allStats.net, prev.allStats.net, true))}
          ${improvementCard("Chất lượng", "Win rate lịch sử", `${data.allStats.winRate.toFixed(1)}%`, data.allStats.winRate >= 50 ? "positive" : "negative", [
            fact("Có WR", `${data.withWr.length}/${data.closed.length}`, "", true),
            fact("WR TB", data.withWr.length ? `${data.avgWr.toFixed(1)}%` : "--", data.avgWr >= 70 ? "positive" : "", true),
            fact("30 lệnh gần", `${data.recentStats.wins}W/${data.recentStats.losses}L`),
          ], delta(data.allStats.winRate, prev.allStats.winRate, true, "%"))}
          ${improvementCard("Rủi ro", "Avg max adverse", data.riskReady.length ? `${data.avgPain.toFixed(2)}R` : "--", data.avgPain >= Number(data.learning.drawdown_pain_r || 0.8) ? "negative" : "", [
            fact("Có telemetry", `${data.riskReady.length}`, "", true),
            fact("Lệnh đau", `${data.painful.length}`, data.painful.length ? "negative" : "positive", true),
            fact("Max lot", `${Number(data.hard.max_lot_per_entry || 0.03).toFixed(2)}`),
          ], delta(data.avgPain, prev.avgPain, false, "R"))}
          ${improvementCard("Tự học", "Lookback", `${Number(data.learning.lookback_days || 90)} ngày`, "", [
            fact("Nâng WR sau", `${Number(data.learning.raise_threshold_min_samples || 5)} mẫu`, "", true),
            fact("Chặn sau", `${Number(data.learning.block_min_samples || 10)} mẫu`, "", true),
            fact("Lệnh nhồi", `${data.addons.length} · ${fmtMoney(data.addonStats.net)}`, clsPnl(data.addonStats.net), true),
          ], delta(data.addonStats.net, prev.addonStats.net, true), false)}
        </div>
      `;
    };
    const groupBy = (items, keyFn) => {
      const groups = new Map();
      for (const item of items) {
        const key = keyFn(item);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
      }
      return groups;
    };
    const statsRow = (label, stats, compact = false, rowClass = "", rowAttrs = "") => {
      const base = [
        [label],
        [stats.total, "num"],
        [stats.wins, "num"],
        [stats.losses, "num"],
        [`${stats.winRate.toFixed(1)}%`, "num"],
        [`<span class="${clsPnl(stats.net)}">${fmtMoney(stats.net)}</span>`, "num"],
      ];
      if (!compact) {
        base.push(
          [`<span class="positive">${fmtMoney(stats.avgWin)}</span>`, "num"],
          [`<span class="negative">${fmtMoney(stats.avgLoss)}</span>`, "num"],
        );
      }
      return row(base, rowClass, rowAttrs);
    };
    const learningActionBadge = (action) => {
      const value = String(action || "WATCH").toUpperCase();
      const klass = value === "BLOCK" ? "closed" : value === "RAISE_WR" ? "sell" : value === "ALLOW" ? "buy" : "open";
      return badge(value, klass);
    };
    const learningStatsRow = (label, item, dimension = "") => {
      const stats = item?.stats || {};
      return row([
        [dimension || item?.dimension || "--"],
        [escapeHtml(label || item?.label || "--")],
        [Number(stats.trades || 0), "num"],
        [`${Number(stats.win_rate || 0).toFixed(1)}%`, "num"],
        [`<span class="${clsPnl(Number(stats.net_pnl || 0))}">${fmtMoney(stats.net_pnl || 0)}</span>`, "num"],
        [`${Number(stats.avg_max_adverse_r || 0).toFixed(3)}R`, "num"],
      ]);
    };
    const renderLearningReport = (learning) => {
      if (!learning) {
        ["learning-watch-body", "learning-edge-body", "learning-management-body"].forEach(id => {
          document.getElementById(id).innerHTML = `<tr><td colspan="7" class="empty">Chưa có dữ liệu learning.</td></tr>`;
        });
        return;
      }
      const watch = learning.watchlist || [];
      setText("learning-watch-meta", `${watch.length} nhóm cần chú ý · ${learning.lookback_days || 90} ngày`);
      document.getElementById("learning-watch-body").innerHTML = watch.length
        ? watch.map(item => {
            const stats = item.stats || {};
            const rec = item.recommendation || {};
            return row([
              [escapeHtml(item.label || "--")],
              [learningActionBadge(rec.action)],
              [Number(stats.trades || 0), "num"],
              [`${Number(stats.win_rate || 0).toFixed(1)}%`, "num"],
              [stats.profit_factor === null || stats.profit_factor === undefined ? "--" : Number(stats.profit_factor).toFixed(2), "num"],
              [`<span class="${clsPnl(Number(stats.net_pnl || 0))}">${fmtMoney(stats.net_pnl || 0)}</span>`, "num"],
              [escapeHtml(rec.reason || "--")],
            ]);
          }).join("")
        : `<tr><td colspan="7" class="empty">Không có nhóm cần chặn/nâng WR trong lookback.</td></tr>`;

      const dims = learning.dimensions || {};
      const edgeRows = [
        ...(dims.setups || []).slice(0, 4).map(item => learningStatsRow(item.label, item, "Setup")),
        ...(dims.sessions || []).slice(0, 3).map(item => learningStatsRow(item.label, item, "Phiên")),
        ...(dims.wr_buckets || []).slice(0, 3).map(item => learningStatsRow(item.label, item, "WR bucket")),
      ];
      const overall = learning.overall || {};
      setText("learning-edge-meta", `${Number(overall.trades || 0)} lệnh · ${fmtMoney(overall.net_pnl || 0)}`);
      document.getElementById("learning-edge-body").innerHTML = edgeRows.length
        ? edgeRows.join("")
        : `<tr><td colspan="6" class="empty">Chưa đủ dữ liệu nhóm.</td></tr>`;

      const management = learning.management || {};
      const managementRows = [
        ["Có BE", management.break_even],
        ["Chưa BE", management.no_break_even],
        ["Đau >= ngưỡng", management.painful_trades],
        ["Run-up >= 0.5R", management.strong_runups],
      ].map(([label, stats]) => row([
        [label],
        [Number(stats?.trades || 0), "num"],
        [`${Number(stats?.win_rate || 0).toFixed(1)}%`, "num"],
        [`<span class="${clsPnl(Number(stats?.net_pnl || 0))}">${fmtMoney(stats?.net_pnl || 0)}</span>`, "num"],
        [stats?.profit_factor === null || stats?.profit_factor === undefined ? "--" : Number(stats.profit_factor).toFixed(2), "num"],
        [`${Number(stats?.avg_max_favorable_r || 0).toFixed(3)}R`, "num"],
      ])).join("");
      setText("learning-management-meta", `BE ${Number(management.break_even?.trades || 0)} · Run-up ${Number(management.strong_runups?.trades || 0)}`);
      document.getElementById("learning-management-body").innerHTML = managementRows;
    };
    const wrQualityClass = (winRate) => {
      if (winRate >= 70) return "positive";
      if (winRate >= 45) return "amber";
      return "negative";
    };
    const winRateCell = (info) => {
      if (!info || !info.stats || !info.stats.total) {
        return `<span class="wr-cell"><span>--</span><small>--</small></span>`;
      }
      const stats = info.stats;
      const klass = wrQualityClass(stats.winRate);
      const title = info.scope === "exact"
        ? "WR cùng loại + cặp + side"
        : "WR theo loại lệnh";
      const suffix = info.scope === "calculated" ? "calc" : `n${stats.total}`;
      return `<span class="wr-cell" title="${title}"><span class="${klass}">${stats.winRate.toFixed(1)}%</span><small>${suffix}</small></span>`;
    };
    const winRateForPosition = (position, trade, closedTrades) => {
      if (trade?.estimated_win_rate === null || trade?.estimated_win_rate === undefined || trade?.estimated_win_rate === "") return null;
      const calculated = Number(trade?.estimated_win_rate);
      if (Number.isFinite(calculated)) return { stats: { winRate: calculated, total: 1 }, scope: "calculated" };
      return null;
    };
    const winRateForTrade = (trade) => {
      if (trade?.estimated_win_rate === null || trade?.estimated_win_rate === undefined || trade?.estimated_win_rate === "") return null;
      const calculated = Number(trade.estimated_win_rate);
      if (Number.isFinite(calculated)) return { stats: { winRate: calculated, total: 1 }, scope: "calculated" };
      return null;
    };
    const plannedPnl = (position, exitPrice, specs) => {
      if (!position || !exitPrice) return null;
      const spec = specs[position.symbol];
      if (!spec || !spec.trade_tick_size || !spec.trade_tick_value) return null;
      const entry = Number(position.entry_price);
      const exit = Number(exitPrice);
      const volume = Number(position.volume || 0);
      const direction = position.side === "BUY" ? 1 : -1;
      return ((exit - entry) * direction / Number(spec.trade_tick_size)) * Number(spec.trade_tick_value) * volume;
    };
    async function getJson(url, timeoutMs = FETCH_TIMEOUT_MS) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const res = await fetch(url, { cache: "no-store", signal: controller.signal });
        if (!res.ok) throw new Error(`${url}: ${res.status}`);
        return res.json();
      } finally {
        clearTimeout(timeout);
      }
    }
    async function patchJson(url, body) {
      const res = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${url}: ${res.status} ${detail}`);
      }
      return res.json();
    }
    const summarizeSymbols = (status) => {
      const states = status.symbol_states || {};
      return Object.entries(states).map(([base, item]) => `${base}:${item.symbol || "--"} ${item.state || "--"}`).join(" | ") || "--";
    };
    const updateRuntimePanel = (status, health) => {
      const healthy = health && health.healthy === true;
      const symbolsHealth = health?.symbols ? Object.values(health.symbols) : [health || {}];
      const mt5Connected = symbolsHealth.some(item => item.mt5_connected === true);
      const workerStates = Object.values(status.symbol_states || {});
      const workerRunning = status.state === "RUNNING" && (!workerStates.length || workerStates.every(item => item.state === "RUNNING"));
      setHtml("rt-api", badge("ONLINE", "open"));
      setHtml("rt-worker", badge(workerRunning ? "RUNNING" : (status.state || "STOPPED"), workerRunning ? "buy" : "failed"));
      setHtml("rt-mt5", badge(mt5Connected ? "CONNECTED" : "DISCONNECTED", mt5Connected ? "buy" : "failed"));
      setHtml("rt-mode", badge(`${status.mode || "--"}${status.live_trading_enabled ? " / LIVE ENABLED" : ""}`, status.live_trading_enabled ? "sell" : "open"));
      setText("rt-symbols", summarizeSymbols(status));
      setText("runtime-meta", status.care_warning ? "CANH BAO: mat cham soc lenh" : healthy ? "Healthy" : "Can kiem tra");
    };
    const updateRecoveryModeLabel = (status) => {
      const recovery = status?.recovery_mode || {};
      const mode = String(recovery.mode || "normal").toLowerCase();
      const label = document.getElementById("recovery-mode-label");
      const textEl = document.getElementById("recovery-mode-text");
      const help = document.getElementById("recovery-mode-help");
      const modeText = mode === "hard" ? "Recovery: Hard" : mode === "soft" ? "Recovery: Soft" : "Recovery: Normal";
      textEl.textContent = modeText;
      label.classList.remove("normal", "soft", "hard");
      label.classList.add(mode === "hard" ? "hard" : mode === "soft" ? "soft" : "normal");
      const loss = Number(recovery.trigger_loss || 0);
      const recovered = Number(recovery.recovered_pnl || 0);
      const ratio = Number(recovery.recovered_ratio || 0) * 100;
      help.setAttribute("data-tip", recovery.active
        ? `Chỉ xét basket đã đóng gần nhất.\nBasket gần nhất có ${recovery.trigger_position_count || 0} lệnh và lỗ ${fmtMoney(loss)}.\nĐã gỡ ${fmtMoney(recovered)} (${ratio.toFixed(0)}%).\nHard: chưa gỡ 50%, cần WR >= 75%.\nSoft: gỡ 50%-100%, cần WR >= 72%.\nNormal: gỡ đủ 100%.\nVí dụ: lỗ -7u, gỡ +3.5u -> Soft; gỡ +7u -> Normal.`
        : `Chỉ xét basket đã đóng gần nhất.\nNếu basket đó lỗ và có >= 7 lệnh thì bật Recovery.\nHard: chưa gỡ 50%, setup cần WR >= 75%.\nSoft: gỡ 50%-100%, setup cần WR >= 72%.\nNormal: basket gần nhất lời/không đủ 7 lệnh, hoặc đã gỡ đủ 100%.\nVí dụ: lỗ -7u, gỡ +3.5u -> Soft; gỡ +7u -> Normal.`);
    };
    const logTime = (value) => {
      if (!value) return "--";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? "--" : date.toLocaleTimeString("vi-VN");
    };
    const escapeHtml = (value) => String(value || "").replace(/[<>&]/g, ch => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[ch]));
    const loadSystemLogs = async () => {
      const data = await getJson("/logs/system?limit=90");
      const lines = (data.entries || []).slice().reverse().map(item => {
        const level = String(item.level || "INFO").toLowerCase();
        return `<div class="log-line"><span class="log-time">${logTime(item.timestamp)}</span><span class="level-${level}">${item.level || "INFO"}</span><span class="log-file">${item.file || "--"}</span><span class="log-msg">${escapeHtml(item.message)}</span></div>`;
      }).join("");
      document.getElementById("system-log-body").innerHTML = lines || `<div class="empty">Chưa có log.</div>`;
      setText("logs-meta", `${data.entries?.length || 0} dong moi nhat`);
    };
    async function refreshSlowData() {
      if (slowDataLoading) return;
      slowDataLoading = true;
      try {
        const [trades, signal, specs, config, learning] = await Promise.all([
          getJson("/trades").catch(() => cachedTrades),
          getJson("/signals/latest").catch(() => cachedSignal),
          getJson("/symbol-specs").catch(() => cachedSpecs),
          getJson("/config").catch(() => cachedConfig),
          getJson("/statistics/learning").catch(() => cachedLearning),
        ]);
        cachedTrades = Array.isArray(trades) ? trades : [];
        cachedSignal = signal || null;
        cachedSpecs = specs || {};
        cachedConfig = config || null;
        cachedLearning = learning || null;
        slowDataVersion += 1;
        lastSlowRefreshAt = Date.now();
      } finally {
        slowDataLoading = false;
      }
    }
    function row(cells, rowClass = "", rowAttrs = "") {
      return `<tr${rowClass ? ` class="${rowClass}"` : ""}${rowAttrs ? ` ${rowAttrs}` : ""}>${cells.map(([html, klass]) => `<td class="${klass || ""}">${html}</td>`).join("")}</tr>`;
    }
    async function loadDashboard() {
      const shouldRefreshSlowData = Date.now() - lastSlowRefreshAt >= SLOW_REFRESH_MS;
      if (shouldRefreshSlowData) refreshSlowData();
      const [status, health, positions, daily, account] = await Promise.all([
        getJson("/status"),
        getJson("/health").catch(() => null),
        getJson("/positions"),
        getJson("/statistics/daily"),
        getJson("/account").catch(() => null),
      ]);
      const trades = cachedTrades;
      const signal = cachedSignal;
      const specs = cachedSpecs;
      const config = cachedConfig;
      const learning = cachedLearning;
      const shouldRenderSlowData = renderedSlowDataVersion !== slowDataVersion;
      cachedPositions = Array.isArray(positions) ? positions : [];

      setText("bot-state", status.state || "--");
      if (status.care_warning) {
        const affected = Object.keys(status.care_warning_symbols || {}).join(", ") || "--";
        setHtml("bot-reason", `<span class="negative">CANH BAO mat cham soc: ${affected}</span>`);
      } else {
        setText("bot-reason", status.state_reason || "--");
      }
      updateRuntimePanel(status, health);
      updateRecoveryModeLabel(status);
      const openCount = positions.length;
      const openLots = positions.reduce((sum, p) => sum + Number(p.volume || 0), 0);
      const positionFloating = positions.reduce((sum, p) => sum + Number(p.profit || 0), 0);
      const accountFloating = account ? Number(account.equity || 0) - Number(account.balance || 0) : null;
      const floating = Number.isFinite(accountFloating) ? accountFloating : positionFloating;
      const configuredOpenLimit = Number(config?.position_control?.max_open_positions || currentGlobalOpenPositions);
      setText("open-count", configuredOpenLimit > 0 ? `${openCount}/${configuredOpenLimit}` : String(openCount));
      setText("open-lots", `${openLots.toFixed(2)} lot`);
      setMoney("floating-pnl", floating);
      if (account) {
        setPlainMoney("account-balance", account.balance);
        setText("account-detail", `Equity ${fmtMoney(account.equity)} · ${account.currency || "USD"}`);
      } else {
        setText("account-balance", "--");
        setText("account-detail", "Chưa kết nối MT5");
      }

      const today = daily && daily.length ? daily[0] : {};
      const storedRealized = Number(today.realized_pnl);
      const storedFloating = Number(today.floating_pnl);
      const realized = Number.isFinite(storedRealized)
        ? storedRealized
        : 0;
      const floatingDaily = Number.isFinite(storedFloating)
        ? storedFloating
        : Number.isFinite(floating)
        ? floating
        : 0;
      setMoney("daily-pnl", realized + floatingDaily);
      setHtml(
        "daily-detail",
        `Realized <span class="${clsPnl(realized)}">${fmtMoney(realized)}</span> · Floating <span class="${clsPnl(floatingDaily)}">${fmtMoney(floatingDaily)}</span>`
      );

      if (config) {
        const target = config.daily_risk?.daily_profit_target_usd ?? config.daily_risk?.daily_profit_target_percent ?? "--";
        const loss = config.daily_risk?.max_daily_loss_usd ?? config.daily_risk?.max_daily_loss_percent ?? "--";
        const dailyLossAmount = config.daily_risk?.max_daily_loss_usd ?? (
          account ? Number(account.equity || 0) * Number(config.daily_risk?.max_daily_loss_percent || 0) / 100 : Number(config.daily_risk?.max_daily_loss_percent || 0)
        );
        currentDailyTargetUsd = config.daily_risk?.daily_profit_target_usd ?? null;
        currentDailyLossUsd = config.daily_risk?.max_daily_loss_usd ?? null;
        const basketTp = config.basket_take_profit || {};
        currentBasketTakeProfitMode = basketTp.mode || "FIXED_USD";
        currentBasketTargetFixedUsd = Number(basketTp.target_fixed_usd || 5);
        currentBasketFastTargetFixedUsd = Number(basketTp.fast_target_fixed_usd || 2);
        currentBasketTargetRMultiple = Number(basketTp.target_r_multiple || 1.5);
        currentBasketTargetEquityPercent = Number(basketTp.target_equity_percent || 1.0);
        if (basketTp.mode === "FIXED_USD") {
          currentBasketTakeProfit = `${basketTp.mode} · ${fmtMoney(Number(basketTp.target_fixed_usd || 0))}`;
          currentFastBasketTakeProfit = `${fmtMoney(Number(basketTp.fast_target_fixed_usd || 0))} fast-only`;
        } else if (basketTp.mode === "R_MULTIPLE") {
          currentBasketTakeProfit = `${basketTp.mode} · ${Number(basketTp.target_r_multiple || 0).toFixed(2)}R`;
          currentFastBasketTakeProfit = `${fmtMoney(Number(basketTp.fast_target_fixed_usd || 0))} fast-only`;
        } else if (basketTp.mode === "EQUITY_PERCENT") {
          currentBasketTakeProfit = `${basketTp.mode} · ${Number(basketTp.target_equity_percent || 0).toFixed(2)}%`;
          currentFastBasketTakeProfit = `${fmtMoney(Number(basketTp.fast_target_fixed_usd || 0))} fast-only`;
        } else {
          currentBasketTakeProfit = "--";
          currentFastBasketTakeProfit = "--";
        }
        const basket = config.basket_stop_loss || {};
        const basketMode = basket.mode || "FIXED_USD";
        currentBasketMode = basketMode;
        currentBasketFixedUsd = Number(basket.maximum_loss_usd || 20);
        currentBasketBalancedRatio = Number(basket.balanced_daily_loss_ratio || 0.2);
        currentBasketBalancedFloor = Number(basket.balanced_minimum_loss_usd || 3);
        const rawBasketValue = basketMode === "BALANCED_DAILY"
          ? Math.max(Number(basket.balanced_minimum_loss_usd || 0), Number(dailyLossAmount || 0) * Number(basket.balanced_daily_loss_ratio || 0))
          : Number(basket.maximum_loss_usd || 0);
        const hardBasketLoss = Number(basket.hard_max_loss_usd || 0);
        const basketValue = hardBasketLoss > 0 ? Math.min(rawBasketValue, hardBasketLoss) : rawBasketValue;
        currentBasketStopLoss = `${basketMode} · ${fmtMoney(basketValue)}`;
        setText("basket-win-value", currentBasketTakeProfit);
        setText("basket-win-detail", `Thường: ${currentBasketTakeProfit} · Fast-only: ${currentFastBasketTakeProfit}`);
        setText("basket-loss-value", currentBasketStopLoss);
        setText("basket-loss-detail", basketMode === "BALANCED_DAILY"
          ? `Tỷ lệ ${Number(currentBasketBalancedRatio).toFixed(2)} · sàn ${fmtMoney(currentBasketBalancedFloor)} · raw ${fmtMoney(rawBasketValue)}${hardBasketLoss > 0 ? ` · hard cap ${fmtMoney(hardBasketLoss)}` : ""}`
          : "Mức lỗ cố định cho 1 nhóm lệnh");
        const fastWinRate = config.fast_scalp?.minimum_historical_win_rate;
        const minTrades = config.fast_scalp?.historical_win_rate_min_trades;
        const hardTrade = config.hard_trade || {};
        currentHardTradeEnabled = Boolean(hardTrade.enabled);
        const hardBtn = document.getElementById("hard-trade-btn");
        const hardText = document.getElementById("hard-trade-text");
        hardText.textContent = currentHardTradeEnabled ? "Hard Trade ON" : "Hard Trade OFF";
        hardBtn.classList.toggle("active", currentHardTradeEnabled);
        const forex = config.forex_trading || {};
        currentForexTradingEnabled = Boolean(forex.enabled);
        currentForexTradingSymbols = Array.isArray(forex.symbols) && forex.symbols.length ? forex.symbols : ["EURUSD", "GBPUSD", "USDJPY"];
        currentGlobalOpenPositions = Number(config?.position_control?.max_open_positions || forex.max_open_positions || 7);
        currentMaxBuyPositions = Number(config?.position_control?.max_buy_positions || 1);
        currentMaxSellPositions = Number(config?.position_control?.max_sell_positions || 1);
        const forexBtn = document.getElementById("forex-mode-btn");
        const forexText = document.getElementById("forex-mode-text");
        forexText.textContent = currentForexTradingEnabled ? "Forex ON" : "Forex OFF";
        forexBtn.classList.toggle("active", currentForexTradingEnabled);
        document.getElementById("target-loss-value").innerHTML = `<span class="positive">+${target}</span> / <span class="negative">-${loss}</span>`;
        setText("quality-rule", currentHardTradeEnabled
          ? `Hard: ${hardTrade.preferred_setup_timeframe || "M30"}>${hardTrade.preferred_entry_timeframe || "M15"} · WR > ${Number(hardTrade.minimum_setup_win_rate || 70).toFixed(0)}% · M5 > ${Number(hardTrade.m5_minimum_setup_win_rate || 80).toFixed(0)}% · ${Number(hardTrade.max_lot_per_entry || 0.03).toFixed(2)} lot/lệnh`
          : (fastWinRate === null || fastWinRate === undefined ? "Hard OFF · Setup WR > 50%" : `Hard OFF · Fast WR = ${fastWinRate}% · sample = ${minTrades} lệnh`));
      }

      const positionsBody = document.getElementById("positions-body");
      const positionsEmpty = document.getElementById("positions-empty");
      const tradeByTicket = new Map(trades.filter(t => t.broker_ticket).map(t => [String(t.broker_ticket), t]));
      const closedTrades = trades.filter(isClosedTrade);
      const sortedPositions = positions
        .map(position => ({ position, trade: tradeByTicket.get(String(position.ticket)) || {} }))
        .sort((a, b) => {
          const openedA = parseTime(a.trade.opened_at)?.getTime() || 0;
          const openedB = parseTime(b.trade.opened_at)?.getTime() || 0;
          if (openedA !== openedB) return openedB - openedA;
          return Number(b.position.ticket || 0) - Number(a.position.ticket || 0);
        });
      positionsBody.innerHTML = sortedPositions.map(({ position: p, trade }) => {
        return row([
          [p.ticket, "left"],
          [`<span class="type-cell">${typeFromKey(trade.idempotency_key)}</span>`, "left"],
          [fmtOpenTime(trade.opened_at), "num time-cell"],
          [winRateCell(winRateForPosition(p, trade, closedTrades)), "num"],
          [symbolCell(p.symbol), "left"],
          [badge(p.side, String(p.side).toLowerCase()), "center"],
          [fmtNum(p.volume, 2), "num"],
          [priceCell(p.entry_price), "num"],
          [priceCell(p.current_price), "num"],
          [fmtPriceWithPnl(p.stop_loss, plannedPnl(p, p.stop_loss, specs)), "num"],
          [fmtPriceWithPnl(p.take_profit, plannedPnl(p, p.take_profit, specs)), "num"],
          [moneyCell(p.profit), "num"],
        ]);
      }).join("");
      positionsEmpty.style.display = positions.length ? "none" : "block";
      setText("positions-meta", `${positions.length} vị thế · Net ${fmtMoney(floating)} · Gross ${fmtMoney(positionFloating)}`);

      if (shouldRenderSlowData) {
      if (signal) {
        setText("signal-time", fmtTime(signal.timestamp));
        setText("sig-symbol", signal.symbol || "--");
        setText("sig-decision", signal.decision || "--");
        setText("sig-side", `${signal.side || "--"} / ${signal.trend || "--"}`);
        setText("sig-score", signal.score === null || signal.score === undefined ? "--" : Number(signal.score).toFixed(0));
        setText("sig-reason", signal.rejection_reason || "Đã mở lệnh / tín hiệu hợp lệ");
      }

      const recentTrades = trades.slice(0, 80);
      const byType = groupBy(closedTrades, t => typeFromKey(t.idempotency_key));
      const typeOrder = ["Fast M1", "Setup M5", "Setup M15", "--"];
      const typeRows = typeOrder
        .filter(key => byType.has(key))
        .map(key => statsRow(key === "--" ? "Khác" : key, buildStats(byType.get(key))));
      typeRows.push(statsRow("Tổng", buildStats(closedTrades)));
      document.getElementById("type-stats-body").innerHTML = typeRows.join("");
      setText("type-stats-meta", `${closedTrades.length} lệnh đã đóng`);

      const bySymbol = Array.from(groupBy(closedTrades, t => String(t.symbol || "--").toUpperCase()).entries())
        .sort(([a], [b]) => String(a).localeCompare(String(b)));
      const forexEntries = bySymbol.filter(([symbol]) => FOREX_SYMBOLS.has(symbol));
      const nonForexEntries = bySymbol.filter(([symbol]) => !FOREX_SYMBOLS.has(symbol));
      const symbolRows = nonForexEntries.map(([symbol, items]) => statsRow(symbol, buildStats(items)));
      const forexTrades = forexEntries.flatMap(([, items]) => items);
      const forexEntryMap = new Map(forexEntries);
      const forexSymbolsForStats = Array.from(new Set([
        ...currentForexTradingSymbols.map(symbol => String(symbol || "").toUpperCase()).filter(symbol => FOREX_SYMBOLS.has(symbol)),
        ...forexEntries.map(([symbol]) => symbol),
      ])).sort((a, b) => a.localeCompare(b));
      if (currentForexTradingEnabled || forexTrades.length) {
        symbolRows.push(statsRow("Tiền tệ", buildStats(forexTrades), false, "stats-toggle-row", `data-action="open-forex-stats"`));
      }
      symbolRows.push(statsRow("Tổng", buildStats(closedTrades)));
      document.getElementById("symbol-stats-body").innerHTML = symbolRows.join("");
      const visibleGroups = nonForexEntries.length + ((currentForexTradingEnabled || forexTrades.length) ? 1 : 0);
      setText("symbol-stats-meta", `${bySymbol.length} cặp · ${closedTrades.length} lệnh đã đóng`);

      const byDay = Array.from(groupBy(closedTrades, t => dayKey(t.closed_at || t.opened_at)).entries())
        .sort(([a], [b]) => String(b).localeCompare(String(a)))
        .slice(0, 14);
      document.getElementById("day-stats-body").innerHTML = byDay
        .map(([day, items]) => statsRow(day, buildStats(items), true))
        .join("");
      setText("day-stats-meta", `${byDay.length} ngày g?n nh?t`);
      renderImprovementPanel(trades, positions, config || {});
      renderLearningReport(learning);

      document.getElementById("trades-body").innerHTML = recentTrades.map(t => row([
        [t.id],
        [t.broker_ticket || "--"],
        [`<span class="type-cell">${typeFromKey(t.idempotency_key)}</span>`],
        [winRateCell(winRateForTrade(t)), "num"],
        [symbolCell(t.symbol)],
        [badge(t.side, String(t.side).toLowerCase())],
        [badge(t.state, String(t.state).toLowerCase())],
        [closeReasonCell(t)],
        [fmtNum(t.initial_volume ?? t.volume, 2), "num"],
        [fmtNum(t.entry_price), "num"],
        [fmtNum(t.initial_stop_loss ?? t.stop_loss), "num"],
        [fmtNum(t.take_profit), "num"],
         [`<span class="${clsPnl(tradePnl(t))}">${fmtMoney(tradePnl(t))}</span>`, "num"],
        [fmtTime(t.opened_at)],
        [fmtTime(t.closed_at)],
      ])).join("");
      setText("trades-meta", `${recentTrades.length} lệnh gần nhất`);
      renderedSlowDataVersion = slowDataVersion;
      }
      setText("last-updated", `Cập nhật: ${new Date().toLocaleTimeString("vi-VN")}`);
      const nowMs = Date.now();
      if (nowMs - lastLogRefreshAt >= LOG_REFRESH_MS) {
        lastLogRefreshAt = nowMs;
        loadSystemLogs().catch(() => setText("logs-meta", "Không tải được log"));
      }
    }
    function openDailyRiskModal() {
      document.getElementById("daily-target-input").value = currentDailyTargetUsd ?? "15";
      document.getElementById("daily-loss-input").value = currentDailyLossUsd ?? "100";
      document.getElementById("daily-risk-status").textContent = `Hiện tại: target ${fmtMoney(currentDailyTargetUsd || 0)} · max loss ${fmtMoney(currentDailyLossUsd || 0)}.`;
      document.getElementById("daily-risk-status").className = "settings-status";
      const modal = document.getElementById("daily-risk-modal");
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
      setTimeout(() => document.getElementById("daily-target-input").focus(), 0);
    }
    function closeDailyRiskModal() {
      const modal = document.getElementById("daily-risk-modal");
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }
    document.getElementById("target-btn").addEventListener("click", openDailyRiskModal);
    document.getElementById("daily-risk-close").addEventListener("click", closeDailyRiskModal);
    document.getElementById("daily-risk-cancel").addEventListener("click", closeDailyRiskModal);
    document.getElementById("daily-risk-modal").addEventListener("click", (event) => {
      if (event.target.id === "daily-risk-modal") closeDailyRiskModal();
    });
    document.getElementById("daily-risk-save").addEventListener("click", async () => {
      const statusEl = document.getElementById("daily-risk-status");
      const target = Number(document.getElementById("daily-target-input").value);
      const loss = Number(document.getElementById("daily-loss-input").value);
      if (!Number.isFinite(target) || target <= 0) {
        statusEl.textContent = "Target phải là số lớn hơn 0.";
        statusEl.className = "settings-status negative";
        return;
      }
      if (!Number.isFinite(loss) || loss <= 0) {
        statusEl.textContent = "Mức lỗ phải là số lớn hơn 0.";
        statusEl.className = "settings-status negative";
        return;
      }
      try {
        statusEl.textContent = "Đang lưu...";
        statusEl.className = "settings-status";
        await patchJson("/config/daily-risk", {
          daily_profit_target_usd: target,
          max_daily_loss_usd: loss,
        });
        await refreshSlowData();
        await loadDashboard();
        statusEl.textContent = `Đã cập nhật: target ${fmtMoney(target)} · max loss ${fmtMoney(loss)}.`;
        statusEl.className = "settings-status positive";
        closeDailyRiskModal();
      } catch (error) {
        showError(error);
        statusEl.textContent = `Không cập nhật được: ${error.message}`;
        statusEl.className = "settings-status negative";
      }
    });
    function openPositionLimitModal() {
      document.getElementById("position-limit-input").value = String(currentGlobalOpenPositions || 2);
      document.getElementById("position-limit-status").textContent = `Hiện tại: tối đa ${currentGlobalOpenPositions || 2} lệnh.`;
      const modal = document.getElementById("position-limit-modal");
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
      setTimeout(() => document.getElementById("position-limit-input").focus(), 0);
    }
    function closePositionLimitModal() {
      const modal = document.getElementById("position-limit-modal");
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }
    document.getElementById("position-limit-btn").addEventListener("click", openPositionLimitModal);
    document.getElementById("position-limit-close").addEventListener("click", closePositionLimitModal);
    document.getElementById("position-limit-cancel").addEventListener("click", closePositionLimitModal);
    document.getElementById("position-limit-modal").addEventListener("click", (event) => {
      if (event.target.id === "position-limit-modal") closePositionLimitModal();
    });
    document.getElementById("position-limit-save").addEventListener("click", async () => {
      const statusEl = document.getElementById("position-limit-status");
      const total = Number(document.getElementById("position-limit-input").value);
      if (!Number.isInteger(total) || total < 1) {
        statusEl.textContent = "Giá trị phải là số nguyên >= 1.";
        statusEl.className = "settings-status negative";
        return;
      }
      try {
        statusEl.textContent = "Đang lưu...";
        statusEl.className = "settings-status";
        await patchJson("/config/position-control", {
          max_open_positions: total,
          max_buy_positions: total,
          max_sell_positions: total,
        });
        await refreshSlowData();
        await loadDashboard();
        statusEl.textContent = `Đã cập nhật: tối đa ${total} lệnh, tính chung cả BUY và SELL.`;
        statusEl.className = "settings-status positive";
        closePositionLimitModal();
      } catch (error) {
        showError(error);
        statusEl.textContent = `Không cập nhật được: ${error.message}`;
        statusEl.className = "settings-status negative";
      }
    });
    document.getElementById("basket-win-btn").addEventListener("click", async () => {
      const modeInput = prompt("Basket Win mode: FIXED_USD, R_MULTIPLE ho?c EQUITY_PERCENT", currentBasketTakeProfitMode || "FIXED_USD");
      if (modeInput === null) return;
      const mode = String(modeInput).trim().toUpperCase();
      const body = {};
      if (mode === "FIXED_USD") {
        const fixedInput = prompt("Basket win cho nhóm thu?ng USD:", String(currentBasketTargetFixedUsd || 5));
        if (fixedInput === null) return;
        const fastInput = prompt("Basket win cho nhóm fast-only USD:", String(currentBasketFastTargetFixedUsd || 2));
        if (fastInput === null) return;
        const fixed = Number(fixedInput);
        const fast = Number(fastInput);
        if (!Number.isFinite(fixed) || fixed <= 0 || !Number.isFinite(fast) || fast <= 0) {
          alert("Giá trị phải lớn hơn 0.");
          return;
        }
        body.mode = "FIXED_USD";
        body.target_fixed_usd = fixed;
        body.fast_target_fixed_usd = fast;
      } else if (mode === "R_MULTIPLE") {
        const rInput = prompt("M?c tiêu R cho basket thu?ng:", String(currentBasketTargetRMultiple || 1.5));
        if (rInput === null) return;
        const fastInput = prompt("Basket win cho nhóm fast-only USD:", String(currentBasketFastTargetFixedUsd || 2));
        if (fastInput === null) return;
        const r = Number(rInput);
        const fast = Number(fastInput);
        if (!Number.isFinite(r) || r <= 0 || !Number.isFinite(fast) || fast <= 0) {
          alert("Giá trị phải lớn hơn 0.");
          return;
        }
        body.mode = "R_MULTIPLE";
        body.target_r_multiple = r;
        body.fast_target_fixed_usd = fast;
      } else if (mode === "EQUITY_PERCENT") {
        const pInput = prompt("M?c tiêu % equity cho basket thu?ng:", String(currentBasketTargetEquityPercent || 1.0));
        if (pInput === null) return;
        const fastInput = prompt("Basket win cho nhóm fast-only USD:", String(currentBasketFastTargetFixedUsd || 2));
        if (fastInput === null) return;
        const p = Number(pInput);
        const fast = Number(fastInput);
        if (!Number.isFinite(p) || p <= 0 || !Number.isFinite(fast) || fast <= 0) {
          alert("Giá trị phải lớn hơn 0.");
          return;
        }
        body.mode = "EQUITY_PERCENT";
        body.target_equity_percent = p;
        body.fast_target_fixed_usd = fast;
      } else {
        alert("Mode không h?p l?.");
        return;
      }

      try {
        await patchJson("/config/basket-take-profit", body);
        await loadDashboard();
        alert("Đã cập nhật basket win.");
      } catch (error) {
        showError(error);
        alert(`Không cập nhật được basket win: ${error.message}`);
      }
    });
    document.getElementById("hard-trade-btn").addEventListener("click", async () => {
      const nextEnabled = !currentHardTradeEnabled;
      try {
        await patchJson("/config/hard-trade", {
          enabled: nextEnabled,
          minimum_setup_win_rate: 70,
          m5_minimum_setup_win_rate: 80,
          max_lot_per_entry: 0.03,
          max_open_positions: 7,
          allow_fast_scalp: false,
          scan_interval_seconds: 1,
          position_monitor_interval_seconds: 1,
          preferred_setup_timeframe: "M30",
          preferred_entry_timeframe: "M15",
        });
        await refreshSlowData();
        await loadDashboard();
      } catch (error) {
        showError(error);
        alert(`Không cập nhật được Hard Trade: ${error.message}`);
      }
    });
    document.getElementById("forex-mode-btn").addEventListener("click", async () => {
      const nextEnabled = !currentForexTradingEnabled;
      const message = nextEnabled
        ? `Bật Forex mode cho ${currentForexTradingSymbols.join(", ")} trong trần chung ${currentGlobalOpenPositions} lệnh. Bot sẽ tự nạp lại runtime ngay. Tiếp tục?`
        : "Tắt Forex mode. Bot sẽ chỉ chặn lệnh forex mới, còn lệnh đang mở vẫn được chăm sóc. Tiếp tục?";
      if (!confirm(message)) return;
      try {
        const result = await patchJson("/config/forex-trading", {
          enabled: nextEnabled,
          symbols: currentForexTradingSymbols,
          max_open_positions: currentGlobalOpenPositions,
        });
        await refreshSlowData();
        await loadDashboard();
        const activeSymbols = result.runtime_symbols ? Object.values(result.runtime_symbols).join(", ") : "--";
        alert(`Đã ${nextEnabled ? "bật" : "tắt"} Forex mode và áp dụng runtime. Cặp đang chạy: ${activeSymbols}`);
      } catch (error) {
        showError(error);
        alert(`Không cập nhật được Forex mode: ${error.message}`);
      }
    });
    document.getElementById("basket-loss-btn").addEventListener("click", async () => {
      const modeInput = prompt("Basket SL mode: FIXED_USD ho?c BALANCED_DAILY", currentBasketMode || "BALANCED_DAILY");
      if (modeInput === null) return;
      const mode = String(modeInput).trim().toUpperCase();
      const body = {};
      if (mode === "FIXED_USD") {
        const fixedInput = prompt("Basket SL cố định USD:", String(currentBasketFixedUsd || 20));
        if (fixedInput === null) return;
        const fixed = Number(fixedInput);
        if (!Number.isFinite(fixed) || fixed <= 0) {
          alert("Basket SL phải là số lớn hơn 0.");
          return;
        }
        body.mode = "FIXED_USD";
        body.maximum_loss_usd = fixed;
      } else if (mode === "BALANCED_DAILY") {
        const ratioInput = prompt("Tỷ lệ basket loss theo max lỗ ngày (0.01 - 1.0):", String(currentBasketBalancedRatio || 0.2));
        if (ratioInput === null) return;
        const floorInput = prompt("M?c sàn t?i thi?u USD:", String(currentBasketBalancedFloor || 3));
        if (floorInput === null) return;
        const ratio = Number(ratioInput);
        const floor = Number(floorInput);
        if (!Number.isFinite(ratio) || ratio <= 0 || ratio > 1) {
          alert("Tỷ lệ phải nằm trong khoảng 0.01 - 1.0.");
          return;
        }
        if (!Number.isFinite(floor) || floor <= 0) {
          alert("Mức sàn phải lớn hơn 0.");
          return;
        }
        body.mode = "BALANCED_DAILY";
        body.balanced_daily_loss_ratio = ratio;
        body.balanced_minimum_loss_usd = floor;
      } else {
        alert("Mode không h?p l?.");
        return;
      }

      try {
        await patchJson("/config/basket-stop-loss", body);
        await loadDashboard();
        alert("Đã cập nhật basket SL.");
      } catch (error) {
        showError(error);
        alert(`Không cập nhật được basket SL: ${error.message}`);
      }
    });
    async function refreshDashboard() {
      if (dashboardLoading) return;
      dashboardLoading = true;
      try {
        await loadDashboard();
      } catch (error) {
        showError(error);
      } finally {
        dashboardLoading = false;
      }
    }
    function forexSymbolKey(trade) {
      return String(trade?.symbol || "").toUpperCase();
    }
    function renderForexStatsModal() {
      const forexTradesAll = cachedTrades.filter(trade => FOREX_SYMBOLS.has(forexSymbolKey(trade)));
      const forexClosedTrades = forexTradesAll.filter(isClosedTrade);
      const byForexSymbol = groupBy(forexClosedTrades, trade => forexSymbolKey(trade));
      const forexSymbolsForStats = Array.from(new Set([
        ...currentForexTradingSymbols.map(symbol => String(symbol || "").toUpperCase()).filter(symbol => FOREX_SYMBOLS.has(symbol)),
        ...forexTradesAll.map(forexSymbolKey),
      ])).sort((a, b) => a.localeCompare(b));
      document.getElementById("forex-modal-stats-body").innerHTML = forexSymbolsForStats
        .map(symbol => statsRow(symbolCell(symbol), buildStats(byForexSymbol.get(symbol) || [])))
        .join("") || row([[symbolCell("--")], [0, "num"], [0, "num"], [0, "num"], ["0.0%", "num"], [fmtMoney(0), "num"], [fmtMoney(0), "num"], [fmtMoney(0), "num"]]);
      document.getElementById("forex-modal-trades-body").innerHTML = forexTradesAll.map(t => row([
        [t.id],
        [t.broker_ticket || "--"],
        [`<span class="type-cell">${typeFromKey(t.idempotency_key)}</span>`],
        [winRateCell(winRateForTrade(t)), "num"],
        [symbolCell(t.symbol)],
        [badge(t.side, String(t.side).toLowerCase())],
        [badge(t.state, String(t.state).toLowerCase())],
        [closeReasonCell(t)],
        [fmtNum(t.initial_volume ?? t.volume, 2), "num"],
        [fmtNum(t.entry_price), "num"],
        [fmtNum(t.initial_stop_loss ?? t.stop_loss), "num"],
        [fmtNum(t.take_profit), "num"],
        [`<span class="${clsPnl(tradePnl(t))}">${fmtMoney(tradePnl(t))}</span>`, "num"],
        [fmtShortDateTime(t.opened_at)],
        [fmtShortDateTime(t.closed_at)],
      ])).join("") || row([["Chưa có lịch sử giao dịch tiền tệ", "center"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"], ["", "num"]]);
      setText("forex-modal-meta", `${forexTradesAll.length} lệnh tiền tệ · ${forexClosedTrades.length} lệnh đã đóng`);
    }
    function openForexStatsModal() {
      renderForexStatsModal();
      const modal = document.getElementById("forex-stats-modal");
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
    }
    function closeForexStatsModal() {
      const modal = document.getElementById("forex-stats-modal");
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }
    document.querySelectorAll("[data-improvement-range]").forEach(button => {
      button.addEventListener("click", () => {
        activeImprovementRange = button.dataset.improvementRange || "today";
        document.querySelectorAll("[data-improvement-range]").forEach(item => item.classList.toggle("active", item === button));
        renderImprovementPanel(cachedTrades, cachedPositions, cachedConfig || {});
      });
    });
    document.getElementById("refresh-btn").addEventListener("click", refreshDashboard);
    document.getElementById("symbol-stats-body").addEventListener("click", async (event) => {
      const target = event.target.closest("[data-action='open-forex-stats']");
      if (!target) return;
      openForexStatsModal();
    });
    document.getElementById("forex-modal-close").addEventListener("click", closeForexStatsModal);
    document.getElementById("forex-stats-modal").addEventListener("click", (event) => {
      if (event.target.id === "forex-stats-modal") closeForexStatsModal();
    });
    document.getElementById("improvement-compare-btn").addEventListener("click", openImprovementCompareModal);
    document.querySelectorAll("[data-compare-range]").forEach(button => {
      button.addEventListener("click", () => {
        activeCompareRange = button.dataset.compareRange || "day";
        document.querySelectorAll("[data-compare-range]").forEach(item => item.classList.toggle("active", item === button));
        renderImprovementCompareModal();
      });
    });
    document.getElementById("improvement-compare-close").addEventListener("click", closeImprovementCompareModal);
    document.getElementById("improvement-compare-modal").addEventListener("click", (event) => {
      if (event.target.id === "improvement-compare-modal") closeImprovementCompareModal();
    });
    const helpTooltip = document.getElementById("help-tooltip");
    let pinnedHelpDot = null;
    function positionHelpTooltip(dot) {
      const tip = dot?.dataset?.tip || "";
      if (!tip || !helpTooltip) return;
      helpTooltip.textContent = tip;
      helpTooltip.setAttribute("style", [
        "position:fixed",
        "width:min(360px, calc(100vw - 24px))",
        "padding:10px 12px",
        "border:1px solid rgba(255,255,255,.35)",
        "border-radius:12px",
        "background:#000",
        "color:#fff",
        "box-shadow:0 18px 45px rgba(0,0,0,.72)",
        "font-size:12px",
        "line-height:1.45",
        "white-space:pre-wrap",
        "pointer-events:none",
        "z-index:10000",
      ].join(";"));
      helpTooltip.classList.add("open");
      helpTooltip.setAttribute("aria-hidden", "false");
      const rect = dot.getBoundingClientRect();
      const tooltipRect = helpTooltip.getBoundingClientRect();
      const gap = 10;
      let top = rect.bottom + gap;
      let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
      if (top + tooltipRect.height > window.innerHeight - gap) {
        top = Math.max(gap, rect.top - tooltipRect.height - gap);
      }
      left = Math.min(Math.max(gap, left), window.innerWidth - tooltipRect.width - gap);
      helpTooltip.style.top = `${top}px`;
      helpTooltip.style.left = `${left}px`;
      helpTooltip.style.opacity = "1";
      helpTooltip.style.transform = "translateY(0)";
    }
    function hideHelpTooltip(force = false) {
      if (pinnedHelpDot && !force) return;
      pinnedHelpDot = null;
      helpTooltip?.classList.remove("open");
      helpTooltip?.setAttribute("aria-hidden", "true");
      if (helpTooltip) {
        helpTooltip.style.opacity = "0";
        helpTooltip.style.transform = "translateY(4px)";
      }
    }
    document.addEventListener("mouseover", (event) => {
      const dot = event.target.closest(".help-dot[data-tip]");
      if (dot) positionHelpTooltip(dot);
    });
    document.addEventListener("focusin", (event) => {
      const dot = event.target.closest(".help-dot[data-tip]");
      if (dot) positionHelpTooltip(dot);
    });
    document.addEventListener("mouseout", (event) => {
      if (event.target.closest(".help-dot[data-tip]")) hideHelpTooltip();
    });
    document.addEventListener("focusout", (event) => {
      if (event.target.closest(".help-dot[data-tip]")) hideHelpTooltip();
    });
    document.addEventListener("click", (event) => {
      const dot = event.target.closest(".help-dot[data-tip]");
      if (dot) {
        pinnedHelpDot = pinnedHelpDot === dot ? null : dot;
        if (pinnedHelpDot) positionHelpTooltip(dot);
        else hideHelpTooltip(true);
        return;
      }
      hideHelpTooltip(true);
    });
    window.addEventListener("scroll", () => hideHelpTooltip(true), true);
    window.addEventListener("resize", () => pinnedHelpDot ? positionHelpTooltip(pinnedHelpDot) : hideHelpTooltip(true));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hideHelpTooltip(true);
        closeForexStatsModal();
        closeDailyRiskModal();
        closePositionLimitModal();
        closeImprovementCompareModal();
      }
    });
    function showError(error) {
      setText("last-updated", `Lỗi tải dữ liệu: ${error.message}`);
    }
    refreshDashboard();
    setInterval(refreshDashboard, CORE_REFRESH_MS);
  </script>
</body>
</html>"""

