#!/usr/bin/env python3
"""
HTTP-обёртка над run_math_probe: POST /v1/math-probe, GET /health.
Запуск из корня /app в образе subnet-math:

  PROBE_PORT=8091 NETUID=2 WALLET_NAME=math-val python scripts/subnet_probe_http.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_SCRIPTS))

from subnet_probe_lib import run_math_probe  # noqa: E402


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return int(v)


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return float(v)


DEFAULTS = {
    "netuid": lambda: _env_int("NETUID", 1),
    "wallet_name": lambda: os.environ.get("WALLET_NAME", "math-val"),
    "hotkey": lambda: os.environ.get("HOTKEY", "default"),
    "chain_endpoint": lambda: os.environ.get(
        "SUBTENSOR_CHAIN",
        "ws://127.0.0.1:9944",
    ),
    "sample_size": lambda: _env_int("PROBE_SAMPLE_SIZE", 4),
    "operand_a": lambda: _env_int("PROBE_OPERAND_A", 6),
    "operand_b": lambda: _env_int("PROBE_OPERAND_B", 7),
    "op": lambda: os.environ.get("PROBE_OP", "*"),
    "timeout": lambda: _env_float("PROBE_TIMEOUT", 30.0),
}


def _merge_body(body: dict | None) -> dict:
    b = dict(body) if isinstance(body, dict) else {}
    out = {}
    out["netuid"] = int(b.get("netuid", DEFAULTS["netuid"]()))
    out["wallet_name"] = str(b.get("wallet_name", DEFAULTS["wallet_name"]()))
    out["hotkey"] = str(b.get("hotkey", DEFAULTS["hotkey"]()))
    out["chain_endpoint"] = str(
        b.get("chain_endpoint", DEFAULTS["chain_endpoint"]()),
    )
    out["sample_size"] = int(b.get("sample_size", DEFAULTS["sample_size"]()))
    out["operand_a"] = int(b.get("operand_a", DEFAULTS["operand_a"]()))
    out["operand_b"] = int(b.get("operand_b", DEFAULTS["operand_b"]()))
    out["op"] = str(b.get("op", DEFAULTS["op"]()))
    out["timeout"] = float(b.get("timeout", DEFAULTS["timeout"]()))
    if "miner_uids" in b and b["miner_uids"] is not None:
        out["miner_uids"] = [int(x) for x in b["miner_uids"]]
    else:
        out["miner_uids"] = None
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def _send_json(self, status: int, obj: object) -> None:
        try:
            raw = json.dumps(
                obj,
                ensure_ascii=False,
                indent=2,
                default=str,
            ).encode("utf-8")
        except Exception as e:
            raw = json.dumps(
                {"ok": False, "error": f"json_encode: {e}", "type": type(e).__name__},
                ensure_ascii=False,
            ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/health", "/"):
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "subnet-math-probe",
                    "routes": ["GET /health", "POST /v1/math-probe"],
                },
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path != "/v1/math-probe":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                text = (raw.decode("utf-8-sig") or "{}").strip()
                body = json.loads(text or "{}")
            except json.JSONDecodeError as e:
                self._send_json(400, {"ok": False, "error": f"invalid JSON: {e}"})
                return
            if not isinstance(body, dict):
                self._send_json(
                    400,
                    {"ok": False, "error": "JSON body must be an object"},
                )
                return
            kw = _merge_body(body)
            try:
                result = asyncio.run(run_math_probe(**kw))
            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                self._send_json(
                    500,
                    {"ok": False, "error": str(e), "type": type(e).__name__},
                )
                return
            status = 200 if result.get("ok") else 400
            self._send_json(status, result)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            try:
                self._send_json(
                    500,
                    {
                        "ok": False,
                        "error": str(e),
                        "type": type(e).__name__,
                    },
                )
            except Exception:
                pass


def main() -> None:
    port = _env_int("PROBE_PORT", 8091)
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"subnet-math-probe listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
