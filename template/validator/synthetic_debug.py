"""Dump per-round synthetic validator artifacts when VALIDATOR_SYNTHETIC_DEBUG is enabled."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import bittensor as bt


def _safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(x)
    except (TypeError, ValueError):
        return None


def is_enabled() -> bool:
    return (os.environ.get("VALIDATOR_SYNTHETIC_DEBUG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def base_dir() -> Path:
    raw = (os.environ.get("VALIDATOR_SYNTHETIC_DEBUG_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("/app/logs/VALIDATOR_SYNTHETIC_DEBUG")


def new_run_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S_%fZ")
    d = base_dir() / ts
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_frame_png(run_dir: Path, synapse: Any) -> bool:
    """Decode synapse.frame_jpeg_b64 (JPEG) and save as frame.png."""
    b64 = getattr(synapse, "frame_jpeg_b64", None)
    if not b64:
        return False
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return False
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return False
        return bool(cv2.imwrite(str(run_dir / "frame.png"), img))
    except Exception:
        return False


def synapse_request_dict(synapse: Any) -> dict[str, Any]:
    """Payload sent to miners (frame as separate file; avoid multi‑MB JSON)."""
    out: dict[str, Any] = {
        "version": getattr(synapse, "version", None),
        "instruction": getattr(synapse, "instruction", None),
        "task_id": getattr(synapse, "task_id", None),
        "synthetic_context_json": getattr(synapse, "synthetic_context_json", None),
    }
    fj = getattr(synapse, "frame_jpeg_b64", None)
    if fj:
        out["frame_jpeg_b64"] = None
        out["frame_jpeg_b64_note"] = "omitted; see frame.png in this folder when capture succeeded"
    else:
        out["frame_jpeg_b64"] = None
        out["frame_jpeg_b64_note"] = "no frame attached"
    return out


def miner_reply_dict(response: Any) -> dict[str, Any]:
    if response is None:
        return {"error": "null_response"}
    out: dict[str, Any] = {
        "action_id": getattr(response, "action_id", None),
        "confidence": getattr(response, "confidence", None),
        "miner_error": getattr(response, "miner_error", None),
        "miner_response_json": getattr(response, "miner_response_json", None),
    }
    dend = getattr(response, "dendrite", None)
    if dend is not None:
        out["dendrite_status_code"] = getattr(dend, "status_code", None)
        out["dendrite_status_message"] = getattr(dend, "status_message", None)
        out["dendrite_process_time"] = getattr(dend, "process_time", None)
    return out


def write_round_artifacts(
    run_dir: Path,
    *,
    synapse: Any,
    synthetic_context: dict[str, Any],
    miner_uids: Any,
    axons: list[Any],
    responses: list[Any],
    scoreboard: dict[str, Any],
    validator_self: Any,
    ue_extra: Optional[dict[str, Any]],
) -> None:
    try:
        _write_json(run_dir / "request.json", synapse_request_dict(synapse))
    except Exception as e:
        bt.logging.warning(f"synthetic_debug request.json failed: {e!r}")

    try:
        wrote = write_frame_png(run_dir, synapse)
        if not wrote and getattr(synapse, "frame_jpeg_b64", None):
            (run_dir / "frame.png.miss").write_text(
                "frame_jpeg_b64 set but decode/save failed\n", encoding="utf-8"
            )
    except Exception as e:
        bt.logging.warning(f"synthetic_debug frame.png failed: {e!r}")

    try:
        rows = []
        for uid, axon, resp in zip(miner_uids, axons, responses):
            row = miner_reply_dict(resp)
            row["uid"] = int(uid)
            row["axon_ip"] = getattr(axon, "ip", None)
            row["axon_port"] = getattr(axon, "port", None)
            rows.append(row)
        _write_json(run_dir / "miners_replies.json", {"replies": rows})
    except Exception as e:
        bt.logging.warning(f"synthetic_debug miners_replies.json failed: {e!r}")

    try:
        _write_json(run_dir / "scoring.json", scoreboard)
    except Exception as e:
        bt.logging.warning(f"synthetic_debug scoring.json failed: {e!r}")

    try:
        meta: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "synthetic_context": synthetic_context,
            "ue_synthetic": ue_extra,
            "netuid": int(getattr(validator_self.config, "netuid", 0) or 0),
            "validator_step": int(getattr(validator_self, "step", -1)),
            "block": _safe_int(getattr(validator_self, "block", None)),
            "forward_sleep_sec": float(getattr(validator_self.config.neuron, "forward_sleep", 0) or 0),
            "dendrite_timeout_sec": float(getattr(validator_self.config.neuron, "timeout", 0) or 0),
            "sample_size": int(getattr(validator_self.config.neuron, "sample_size", 0) or 0),
            "hotkey": str(getattr(validator_self.wallet.hotkey, "ss58_address", "") or ""),
            "debug_base_dir": str(base_dir()),
        }
        _write_json(run_dir / "metadata.json", meta)
        bt.logging.info(f"VALIDATOR_SYNTHETIC_DEBUG wrote {run_dir}")
    except Exception as e:
        bt.logging.warning(f"synthetic_debug metadata.json failed: {e!r}")
