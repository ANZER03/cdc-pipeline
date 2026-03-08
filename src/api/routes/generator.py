"""Generator control endpoints and simple UI."""

from __future__ import annotations

from textwrap import dedent
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api.dependencies import get_generator_manager
from api.services.generator_manager import GeneratorManager


router = APIRouter(tags=["generator"])


class GeneratorStartRequest(BaseModel):
    mode: Literal["all", "postgres", "kafka"] = "all"
    rate: int = Field(default=10, ge=1, le=500)
    duration: int = Field(default=300, ge=5, le=3600)


@router.get("/generator", response_class=HTMLResponse)
async def generator_page() -> HTMLResponse:
    return HTMLResponse(_generator_html())


@router.get("/api/generator/status")
async def generator_status(
    manager: GeneratorManager = Depends(get_generator_manager),
) -> dict:
    return manager.status


@router.post("/api/generator/start")
async def generator_start(
    payload: GeneratorStartRequest,
    manager: GeneratorManager = Depends(get_generator_manager),
) -> dict:
    try:
        return await manager.start(mode=payload.mode, rate=payload.rate, duration=payload.duration)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/generator/stop")
async def generator_stop(
    manager: GeneratorManager = Depends(get_generator_manager),
) -> dict:
    return await manager.stop()


def _generator_html() -> str:
    return dedent(
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Nexus Generator Control</title>
          <style>
            :root {
              --bg: #f3efe5;
              --panel: rgba(255, 252, 246, 0.88);
              --line: #c8baa4;
              --text: #2a241d;
              --muted: #6b6257;
              --brand: #0f766e;
              --brand-strong: #115e59;
              --warn: #b45309;
              --danger: #b91c1c;
              --ok: #166534;
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              font-family: "Segoe UI", "Helvetica Neue", sans-serif;
              color: var(--text);
              background:
                radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 30%),
                radial-gradient(circle at bottom right, rgba(180, 83, 9, 0.16), transparent 35%),
                var(--bg);
              min-height: 100vh;
            }
            .shell {
              max-width: 980px;
              margin: 0 auto;
              padding: 32px 20px 40px;
            }
            .hero {
              margin-bottom: 22px;
            }
            .eyebrow {
              font-size: 12px;
              letter-spacing: 0.16em;
              text-transform: uppercase;
              color: var(--brand-strong);
              margin-bottom: 10px;
            }
            h1 {
              margin: 0 0 8px;
              font-size: clamp(30px, 5vw, 52px);
              line-height: 0.95;
            }
            .hero p {
              margin: 0;
              max-width: 720px;
              color: var(--muted);
              font-size: 16px;
            }
            .grid {
              display: grid;
              gap: 18px;
              grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            }
            .panel {
              background: var(--panel);
              backdrop-filter: blur(10px);
              border: 1px solid var(--line);
              border-radius: 22px;
              padding: 22px;
              box-shadow: 0 18px 36px rgba(42, 36, 29, 0.08);
            }
            .panel h2 {
              margin: 0 0 14px;
              font-size: 20px;
            }
            .field {
              display: grid;
              gap: 8px;
              margin-bottom: 14px;
            }
            label {
              font-size: 13px;
              text-transform: uppercase;
              letter-spacing: 0.08em;
              color: var(--muted);
            }
            input, select {
              width: 100%;
              padding: 12px 14px;
              border-radius: 14px;
              border: 1px solid var(--line);
              background: rgba(255, 255, 255, 0.9);
              color: var(--text);
              font-size: 15px;
            }
            .actions {
              display: flex;
              gap: 10px;
              flex-wrap: wrap;
              margin-top: 8px;
            }
            button {
              border: 0;
              border-radius: 999px;
              padding: 12px 18px;
              font-size: 14px;
              font-weight: 700;
              cursor: pointer;
            }
            .primary { background: var(--brand); color: white; }
            .secondary { background: #e7ddd0; color: var(--text); }
            .danger { background: var(--danger); color: white; }
            .status-pill {
              display: inline-flex;
              align-items: center;
              gap: 8px;
              padding: 8px 12px;
              border-radius: 999px;
              font-size: 13px;
              font-weight: 700;
              background: #efe6d9;
            }
            .status-pill.running { color: var(--ok); background: rgba(22, 101, 52, 0.12); }
            .status-pill.failed { color: var(--danger); background: rgba(185, 28, 28, 0.12); }
            .status-pill.completed { color: var(--warn); background: rgba(180, 83, 9, 0.12); }
            .stats {
              display: grid;
              gap: 10px;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              margin-top: 16px;
            }
            .stat {
              padding: 14px;
              border-radius: 16px;
              border: 1px solid var(--line);
              background: rgba(255, 255, 255, 0.6);
            }
            .stat small { display: block; color: var(--muted); margin-bottom: 6px; }
            .stat strong { font-size: 18px; }
            pre {
              margin: 0;
              padding: 14px;
              min-height: 280px;
              max-height: 420px;
              overflow: auto;
              border-radius: 18px;
              background: #1f1a17;
              color: #f8f3eb;
              font-size: 12px;
              line-height: 1.5;
            }
            .hint {
              margin-top: 10px;
              color: var(--muted);
              font-size: 14px;
            }
          </style>
        </head>
        <body>
          <div class="shell">
            <div class="hero">
              <div class="eyebrow">Nexus Local Tools</div>
              <h1>Generator Control Desk</h1>
              <p>Use this page to launch or stop synthetic traffic without remembering long CLI commands. Tune the mode, speed, and run duration, then watch live status and recent output.</p>
            </div>

            <div class="grid">
              <section class="panel">
                <h2>Run Settings</h2>
                <form id="generator-form">
                  <div class="field">
                    <label for="mode">Generation Mode</label>
                    <select id="mode" name="mode">
                      <option value="all">All streams</option>
                      <option value="postgres">Postgres only</option>
                      <option value="kafka">Kafka only</option>
                    </select>
                  </div>
                  <div class="field">
                    <label for="rate">Rate Per Second</label>
                    <input id="rate" name="rate" type="number" min="1" max="500" value="10">
                  </div>
                  <div class="field">
                    <label for="duration">Duration In Seconds</label>
                    <input id="duration" name="duration" type="number" min="5" max="3600" value="300">
                  </div>
                  <div class="actions">
                    <button class="primary" type="submit">Start Generation</button>
                    <button class="danger" type="button" id="stop-button">Stop</button>
                    <button class="secondary" type="button" id="refresh-button">Refresh Status</button>
                  </div>
                </form>
                <div class="hint">Tip: use `all` for a full local demo, or isolate `postgres` and `kafka` when tuning one side of the pipeline.</div>
              </section>

              <section class="panel">
                <h2>Live Status</h2>
                <div id="status-pill" class="status-pill">Idle</div>
                <div class="stats">
                  <div class="stat"><small>Started</small><strong id="started-at">-</strong></div>
                  <div class="stat"><small>Finished</small><strong id="finished-at">-</strong></div>
                  <div class="stat"><small>Exit Code</small><strong id="exit-code">-</strong></div>
                  <div class="stat"><small>Last Payload</small><strong id="payload-mode">-</strong></div>
                </div>
                <div class="hint" id="payload-summary">No run summary yet.</div>
              </section>
            </div>

            <section class="panel" style="margin-top: 18px;">
              <h2>Generator Output</h2>
              <pre id="logs">Waiting for generator activity...</pre>
            </section>
          </div>

          <script>
            const statusUrl = '/api/generator/status';
            const startUrl = '/api/generator/start';
            const stopUrl = '/api/generator/stop';
            const logNode = document.getElementById('logs');
            const statusPill = document.getElementById('status-pill');
            const startedAt = document.getElementById('started-at');
            const finishedAt = document.getElementById('finished-at');
            const exitCode = document.getElementById('exit-code');
            const payloadMode = document.getElementById('payload-mode');
            const payloadSummary = document.getElementById('payload-summary');

            function renderStatus(data) {
              statusPill.textContent = data.state.toUpperCase();
              statusPill.className = 'status-pill ' + data.state;
              startedAt.textContent = data.startedAt || '-';
              finishedAt.textContent = data.finishedAt || '-';
              exitCode.textContent = data.lastExitCode ?? '-';
              if (data.lastPayload) {
                payloadMode.textContent = data.lastPayload.mode;
                payloadSummary.textContent = `Rate ${data.lastPayload.rate}/s for ${data.lastPayload.duration}s, ${data.lastPayload.postgres_users} users, ${data.lastPayload.products} products.`;
              } else {
                payloadMode.textContent = '-';
                payloadSummary.textContent = 'No run summary yet.';
              }
              logNode.textContent = data.logLines.length ? data.logLines.join('\n') : 'Waiting for generator activity...';
              logNode.scrollTop = logNode.scrollHeight;
            }

            async function refreshStatus() {
              const response = await fetch(statusUrl);
              renderStatus(await response.json());
            }

            async function startGenerator(event) {
              event.preventDefault();
              const payload = {
                mode: document.getElementById('mode').value,
                rate: Number(document.getElementById('rate').value),
                duration: Number(document.getElementById('duration').value),
              };
              const response = await fetch(startUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
              });
              if (!response.ok) {
                const problem = await response.json();
                alert(problem.detail || 'Unable to start generator');
                return;
              }
              renderStatus(await response.json());
            }

            async function stopGenerator() {
              const response = await fetch(stopUrl, {method: 'POST'});
              renderStatus(await response.json());
            }

            document.getElementById('generator-form').addEventListener('submit', startGenerator);
            document.getElementById('stop-button').addEventListener('click', stopGenerator);
            document.getElementById('refresh-button').addEventListener('click', refreshStatus);

            refreshStatus();
            setInterval(refreshStatus, 2000);
          </script>
        </body>
        </html>
        """
    ).strip()
