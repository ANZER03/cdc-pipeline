"""Minimal monitoring UI for validating live API output."""

from __future__ import annotations

from textwrap import dedent

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["monitor"])


@router.get("/monitor", response_class=HTMLResponse)
async def monitor_page() -> HTMLResponse:
    return HTMLResponse(_monitor_html())


def _monitor_html() -> str:
    return dedent(
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Nexus API Monitor</title>
          <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="min-h-screen bg-slate-950 text-slate-100">
          <div class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">

            <!-- Header -->
            <div class="mb-6 flex flex-col gap-3 border-b border-slate-800 pb-6 md:flex-row md:items-end md:justify-between">
              <div>
                <p class="text-xs uppercase tracking-[0.3em] text-cyan-400">Nexus Test Surface</p>
                <h1 class="mt-2 text-3xl font-semibold">Realtime API Monitor</h1>
                <p class="mt-2 max-w-3xl text-sm text-slate-400">
                  Live view powered entirely by WebSocket — no REST polling.
                </p>
              </div>
              <div class="flex flex-wrap gap-2 text-xs">
                <span id="ws-status" class="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-300">WS connecting</span>
                <a href="/generator" class="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-cyan-300 hover:bg-cyan-500/20">Generator Page</a>
              </div>
            </div>

            <!-- KPI summary row -->
            <div class="mb-6 grid gap-4 lg:grid-cols-4">
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Health</div>
                <div id="health-summary" class="mt-3 text-sm text-slate-200">Waiting for WS...</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Active Users</div>
                <div id="kpi-users" class="mt-3 text-2xl font-bold text-slate-100">—</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Revenue</div>
                <div id="kpi-revenue" class="mt-3 text-2xl font-bold text-slate-100">—</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Last WS Event</div>
                <div id="event-summary" class="mt-3 text-sm text-slate-200">Waiting...</div>
              </div>
            </div>

            <!-- Data panels -->
            <div class="grid gap-4 lg:grid-cols-2">
              <section class="space-y-4">
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Metrics</h2>
                    <span class="text-xs text-slate-500">WS event: metrics</span>
                  </div>
                  <pre id="metrics" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Traffic</h2>
                    <span class="text-xs text-slate-500">WS event: traffic</span>
                  </div>
                  <pre id="traffic" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Activities</h2>
                    <span class="text-xs text-slate-500">WS event: activity</span>
                  </div>
                  <pre id="activities" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Alerts</h2>
                    <span class="text-xs text-slate-500">WS event: alert</span>
                  </div>
                  <pre id="alerts" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
              </section>

              <section class="space-y-4">
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Regions</h2>
                    <span class="text-xs text-slate-500">WS event: regions</span>
                  </div>
                  <pre id="regions" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Flows</h2>
                    <span class="text-xs text-slate-500">WS event: flows</span>
                  </div>
                  <pre id="flows" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Platform</h2>
                    <span class="text-xs text-slate-500">WS event: platform</span>
                  </div>
                  <pre id="platform" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Health + Geo</h2>
                    <span class="text-xs text-slate-500">WS event: health · geo</span>
                  </div>
                  <pre id="health-geo" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300">waiting...</pre>
                </div>
              </section>
            </div>

            <!-- WS event log -->
            <div class="mt-4 rounded-2xl border border-slate-800 bg-slate-900 p-4">
              <div class="mb-3 flex items-center justify-between">
                <h2 class="text-sm font-semibold text-slate-100">WS Event Log</h2>
                <span class="text-xs text-slate-500">WS /ws</span>
              </div>
              <pre id="event-log" class="h-80 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
            </div>

          </div>

          <script>
            // ── helpers ──────────────────────────────────────────────────────
            function pretty(v) { return JSON.stringify(v, null, 2); }
            function setText(id, text) { document.getElementById(id).textContent = text; }
            function setJSON(id, v)   { setText(id, pretty(v)); }

            // ── cached state for combined health+geo panel ────────────────────
            let _lastHealth = null;
            let _lastGeo    = null;

            // ── panel update dispatcher ───────────────────────────────────────
            function applyEvent(eventName, data) {
              switch (eventName) {
                case "metrics":
                  setJSON("metrics", data);
                  setText("kpi-users",   data.activeUsers  ?? "—");
                  setText("kpi-revenue", data.revenue != null ? "$" + Number(data.revenue).toFixed(2) : "—");
                  break;
                case "traffic":
                  setJSON("traffic", data);
                  break;
                case "activity":
                  setJSON("activities", data);
                  break;
                case "alert":
                  setJSON("alerts", data);
                  break;
                case "regions":
                  setJSON("regions", data);
                  break;
                case "flows":
                  setJSON("flows", data);
                  break;
                case "platform":
                  setJSON("platform", data);
                  break;
                case "health":
                  _lastHealth = data;
                  setJSON("health-geo", { health: _lastHealth, geo: _lastGeo });
                  setText("health-summary",
                    "API " + (data.apiClusterStatus || "?") +
                    " · CPU " + Number(data.cpu || 0).toFixed(1) + "%" +
                    " · MEM " + Number(data.memory || 0).toFixed(1) + "%"
                  );
                  break;
                case "geo":
                  _lastGeo = data;
                  setJSON("health-geo", { health: _lastHealth, geo: _lastGeo });
                  break;
              }
            }

            // ── event log ────────────────────────────────────────────────────
            function logEvent(eventName, data) {
              const el   = document.getElementById("event-log");
              const line = "[" + new Date().toISOString() + "] " + eventName + "\\n" + pretty(data) + "\\n\\n";
              el.textContent = line + el.textContent.slice(0, 12000);
              setText("event-summary", eventName + " @ " + new Date().toLocaleTimeString());
            }

            // ── WebSocket connection with exponential back-off ────────────────
            function connectWS() {
              let retryDelay = 1000;
              const maxDelay = 30000;
              const statusEl = document.getElementById("ws-status");

              function setStatus(label, connected) {
                statusEl.textContent = label;
                if (connected) {
                  statusEl.className = "rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-emerald-300";
                } else {
                  statusEl.className = "rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-rose-300";
                }
              }

              function open() {
                const proto = location.protocol === "https:" ? "wss" : "ws";
                const ws = new WebSocket(proto + "://" + location.host + "/ws");

                ws.onopen = function() {
                  retryDelay = 1000;
                  setStatus("WS connected", true);
                };

                ws.onerror = function() {
                  setStatus("WS error", false);
                };

                ws.onclose = function() {
                  setStatus("WS reconnecting (" + (retryDelay / 1000).toFixed(0) + "s)", false);
                  setTimeout(open, retryDelay);
                  retryDelay = Math.min(retryDelay * 2, maxDelay);
                };

                ws.onmessage = function(e) {
                  var msg;
                  try { msg = JSON.parse(e.data); } catch (_) { return; }
                  if (!msg.event || msg.data === undefined) return;
                  applyEvent(msg.event, msg.data);
                  logEvent(msg.event, msg.data);
                };
              }

              open();
            }

            connectWS();
          </script>
        </body>
        </html>
        """
    )
