"""Manage background generator processes for the local control UI."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GeneratorManager:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task[None] | None = None
        self._log_lines: deque[str] = deque(maxlen=200)
        self._lock = asyncio.Lock()
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._last_exit_code: int | None = None
        self._last_payload: dict[str, Any] | None = None

    async def start(self, *, mode: str, rate: int, duration: int) -> dict[str, Any]:
        async with self._lock:
            if self.is_running:
                raise RuntimeError("Generator is already running")

            script_path = Path("/app/scripts/generate_test_data.py")
            env = os.environ.copy()
            command = [
                sys.executable,
                str(script_path),
                "--mode",
                mode,
                "--rate",
                str(rate),
                "--duration",
                str(duration),
            ]

            self._log_lines.clear()
            self._started_at = self._now_iso()
            self._finished_at = None
            self._last_exit_code = None
            self._last_payload = None
            self._append_log(f"Starting generator: {' '.join(command[1:])}")

            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            self._task = asyncio.create_task(self._collect_output())
            return self.status

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            if not self._process or self._process.returncode is not None:
                return self.status

            self._append_log("Stopping generator")
            self._process.send_signal(signal.SIGTERM)

        if self._task is not None:
            await self._task
        return self.status

    async def shutdown(self) -> None:
        await self.stop()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def status(self) -> dict[str, Any]:
        state = "running" if self.is_running else "idle"
        if self._last_exit_code not in (None, 0) and not self.is_running:
            state = "failed"
        elif self._last_exit_code == 0 and not self.is_running and self._finished_at is not None:
            state = "completed"
        return {
            "state": state,
            "startedAt": self._started_at,
            "finishedAt": self._finished_at,
            "lastExitCode": self._last_exit_code,
            "lastPayload": self._last_payload,
            "logLines": list(self._log_lines),
        }

    async def _collect_output(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return

        async for raw_line in self._read_lines(process.stdout):
            line = raw_line.strip()
            if not line:
                continue
            self._append_log(line)
            self._capture_payload(line)

        return_code = await process.wait()
        self._last_exit_code = return_code
        self._finished_at = self._now_iso()
        self._append_log(f"Generator exited with code {return_code}")
        self._process = None
        self._task = None

    async def _read_lines(self, stream: asyncio.StreamReader) -> AsyncIterator[str]:
        while True:
            line = await stream.readline()
            if not line:
                break
            yield line.decode(errors="replace")

    def _capture_payload(self, line: str) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict) and {"mode", "duration", "rate"}.issubset(payload):
            self._last_payload = payload

    def _append_log(self, line: str) -> None:
        self._log_lines.append(line)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
