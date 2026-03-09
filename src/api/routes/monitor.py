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
          <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
        </head>
        <body class="min-h-screen bg-slate-950 text-slate-100">
          <div class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <div class="mb-6 flex flex-col gap-3 border-b border-slate-800 pb-6 md:flex-row md:items-end md:justify-between">
              <div>
                <p class="text-xs uppercase tracking-[0.3em] text-cyan-400">Nexus Test Surface</p>
                <h1 class="mt-2 text-3xl font-semibold">Realtime API Monitor</h1>
                <p class="mt-2 max-w-3xl text-sm text-slate-400">
                  Simple live view for snapshots and SSE events before adapting the full dashboard.
                </p>
              </div>
              <div class="flex flex-wrap gap-2 text-xs">
                <span id="sse-status" class="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-emerald-300">SSE connecting</span>
                <button id="refresh-all" class="rounded-full border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200 hover:bg-slate-800">Refresh All</button>
                <a href="/generator" class="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-cyan-300 hover:bg-cyan-500/20">Generator Page</a>
              </div>
            </div>

            <div class="mb-6 grid gap-4 lg:grid-cols-4">
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Health</div>
                <div id="health-summary" class="mt-3 text-sm text-slate-200">Loading...</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Generator</div>
                <div id="generator-summary" class="mt-3 text-sm text-slate-200">Loading...</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Last Event</div>
                <div id="event-summary" class="mt-3 text-sm text-slate-200">Waiting...</div>
              </div>
              <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">Snapshot Sync</div>
                <div id="snapshot-summary" class="mt-3 text-sm text-slate-200">Idle</div>
              </div>
            </div>

            <div class="grid gap-4 lg:grid-cols-2">
              <section class="space-y-4">
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Metrics</h2>
                    <span class="text-xs text-slate-500">GET /api/metrics</span>
                  </div>
                  <pre id="metrics" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Traffic</h2>
                    <span class="text-xs text-slate-500">GET /api/traffic</span>
                  </div>
                  <pre id="traffic" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Activities</h2>
                    <span class="text-xs text-slate-500">GET /api/activities</span>
                  </div>
                  <pre id="activities" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Alerts</h2>
                    <span class="text-xs text-slate-500">GET /api/alerts</span>
                  </div>
                  <pre id="alerts" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
              </section>

              <section class="space-y-4">
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Regions</h2>
                    <span class="text-xs text-slate-500">GET /api/regions</span>
                  </div>
                  <pre id="regions" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Flows</h2>
                    <span class="text-xs text-slate-500">GET /api/flows</span>
                  </div>
                  <pre id="flows" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Platform</h2>
                    <span class="text-xs text-slate-500">GET /api/platform</span>
                  </div>
                  <pre id="platform" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
                <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4">
                  <div class="mb-3 flex items-center justify-between">
                    <h2 class="text-sm font-semibold text-slate-100">Health + Geo</h2>
                    <span class="text-xs text-slate-500">GET /api/health · /api/geo</span>
                  </div>
                  <pre id="health-geo" class="overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
                </div>
              </section>
            </div>

            <div class="mt-4 rounded-2xl border border-slate-800 bg-slate-900 p-4">
              <div class="mb-3 flex items-center justify-between">
                <h2 class="text-sm font-semibold text-slate-100">SSE Event Log</h2>
                <span class="text-xs text-slate-500">GET /events</span>
              </div>
              <pre id="event-log" class="h-80 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-300"></pre>
            </div>
          </div>

          <script>
            const snapshotTargets = {
              metrics: "/api/metrics",
              traffic: "/api/traffic",
              activities: "/api/activities",
              alerts: "/api/alerts",
              regions: "/api/regions",
              flows: "/api/flows",
              platform: "/api/platform",
              health: "/api/health",
              geo: "/api/geo",
              generator: "/api/generator/status"
            };

            function pretty(value) {
              return JSON.stringify(value, null, 2);
            }

            function render(selector, value) {
              $(selector).text(pretty(value));
            }

            function updateSummary(id, text) {
              $(id).text(text);
            }

            function addEventLog(eventName, payload) {
              const line = `[${new Date().toISOString()}] ${eventName}\\n${pretty(payload)}\\n\\n`;
              const $log = $("#event-log");
              $log.text(line + $log.text().slice(0, 12000));
              updateSummary("#event-summary", `${eventName} @ ${new Date().toLocaleTimeString()}`);
            }

            function refreshAll() {
              updateSummary("#snapshot-summary", "Refreshing...");
              $.when(
                $.getJSON(snapshotTargets.metrics),
                $.getJSON(snapshotTargets.traffic),
                $.getJSON(snapshotTargets.activities),
                $.getJSON(snapshotTargets.alerts),
                $.getJSON(snapshotTargets.regions),
                $.getJSON(snapshotTargets.flows),
                $.getJSON(snapshotTargets.platform),
                $.getJSON(snapshotTargets.health),
                $.getJSON(snapshotTargets.geo),
                $.getJSON(snapshotTargets.generator)
              ).done(function(metrics, traffic, activities, alerts, regions, flows, platform, health, geo, generator) {
                render("#metrics", metrics[0]);
                render("#traffic", traffic[0]);
                render("#activities", activities[0]);
                render("#alerts", alerts[0]);
                render("#regions", regions[0]);
                render("#flows", flows[0]);
                render("#platform", platform[0]);
                render("#health-geo", { health: health[0], geo: geo[0] });

                updateSummary("#health-summary", `API ${health[0].apiClusterStatus || "?"} · CPU ${Number(health[0].cpu || 0).toFixed(1)}% · MEM ${Number(health[0].memory || 0).toFixed(1)}%`);
                updateSummary("#generator-summary", `${generator[0].state} · progress ${Number(generator[0].progress || 0).toFixed(1)}%`);
                updateSummary("#snapshot-summary", `Last refresh ${new Date().toLocaleTimeString()}`);
              }).fail(function(xhr) {
                updateSummary("#snapshot-summary", `Refresh failed (${xhr.status || "network"})`);
              });
            }

            function connectEvents() {
              const source = new EventSource("/events");
              const knownEvents = ["kpi", "traffic", "activity", "regions", "flows", "alert", "platform", "health", "geo"];

              source.onopen = function() {
                $("#sse-status")
                  .removeClass("border-rose-500/30 bg-rose-500/10 text-rose-300")
                  .addClass("border-emerald-500/30 bg-emerald-500/10 text-emerald-300")
                  .text("SSE connected");
              };

              source.onerror = function() {
                $("#sse-status")
                  .removeClass("border-emerald-500/30 bg-emerald-500/10 text-emerald-300")
                  .addClass("border-rose-500/30 bg-rose-500/10 text-rose-300")
                  .text("SSE reconnecting");
              };

              $.each(knownEvents, function(_, eventName) {
                source.addEventListener(eventName, function(event) {
                  let payload = {};
                  try {
                    payload = JSON.parse(event.data);
                  } catch (error) {
                    payload = { raw: event.data };
                  }
                  addEventLog(eventName, payload);
                  refreshAll();
                });
              });
            }

            $(function() {
              $("#refresh-all").on("click", refreshAll);
              render("#metrics", { loading: true });
              render("#traffic", { loading: true });
              render("#activities", { loading: true });
              render("#alerts", { loading: true });
              render("#regions", { loading: true });
              render("#flows", { loading: true });
              render("#platform", { loading: true });
              render("#health-geo", { loading: true });
              refreshAll();
              connectEvents();
              setInterval(refreshAll, 15000);
            });
          </script>
        </body>
        </html>
        """
    )
