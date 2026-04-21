"""Validator-side UE teleport + lit frame capture (UnrealCV), aligned with main-repo dashboard."""

from __future__ import annotations

import base64
import io
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import bittensor as bt
import numpy as np

from template.protocol import DroneNavSynapse


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _sleep_after_teleport() -> float:
    try:
        return float(os.environ.get("OPENFLY_SYNTHETIC_POST_TELEPORT_SLEEP_SEC", "2").strip() or "2")
    except ValueError:
        return 2.0


def _spots_path() -> Path:
    raw = (os.environ.get("OPENFLY_TELEPORT_SPOTS_JSON") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("/app/data/teleport_spots.json")


def _load_spots() -> list[dict[str, Any]]:
    path = _spots_path()
    if not path.is_file():
        bt.logging.warning(f"Teleport spots JSON missing: {path}")
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        bt.logging.warning(f"Teleport spots JSON unreadable {path}: {e!r}")
        return []
    raw = doc.get("spots")
    return list(raw) if isinstance(raw, list) else []


def _set_camera_pose_unrealcv(client: Any, x: float, y: float, z: float, pitch: float, yaw: float, roll: float) -> None:
    """Same coordinate remap as OpenFly-Platform/train/eval.py UEBridge.set_camera_pose."""
    x = x * 100
    y = -y * 100
    z = z * 100
    loc = {"x": x, "y": y, "z": z}
    rot = {"pitch": pitch, "yaw": -yaw, "roll": roll}
    client.request("vset /camera/0/location {x} {y} {z}".format(**loc))
    client.request("vset /camera/1/location {x} {y} {z}".format(**loc))
    client.request("vset /camera/0/rotation {pitch} {yaw} {roll}".format(**rot))
    client.request("vset /camera/1/rotation {pitch} {yaw} {roll}".format(**rot))


def _connect_client() -> Any:
    from unrealcv import Client

    host = (os.environ.get("OPENFLY_UNREALCV_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("OPENFLY_UNREALCV_PORT") or "9030").strip())
    tcp_only = (os.environ.get("OPENFLY_UNREALCV_TCP_ONLY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    unix_path = f"/tmp/unrealcv_{port}.socket"
    use_uds = (
        not tcp_only
        and sys.platform.startswith("linux")
        and os.path.exists(unix_path)
        and _env_bool("OPENFLY_UNREALCV_UDS_ON_ATTACH", False)
    )
    if use_uds:
        c = Client(unix_path, "unix")
    else:
        c = Client((host, port))
    if not c.connect():
        raise RuntimeError(f"UnrealCV connect failed (uds={use_uds} host={host!r} port={port})")
    return c


def _capture_lit_jpeg_b64(client: Any) -> str:
    import cv2

    # City Sample + this UnrealCV build: lit works on /camera/0; /camera/1 returns "Invalid sensor id".
    last_err: str | None = None
    data: bytes | None = None
    for cam in ("0", "1"):
        raw = client.request(f"vget /camera/{cam}/lit png")
        if not raw:
            last_err = f"empty vget /camera/{cam}/lit png"
            continue
        if isinstance(raw, str):
            head = raw.strip().splitlines()[0].strip()
            if head.lower().startswith("error ") or "invalid sensor" in head.lower():
                last_err = head[:500]
                continue
            path = Path(head)
            if not path.is_file():
                last_err = f"vget lit png path missing: {raw!r}"
                continue
            data = path.read_bytes()
            break
        if isinstance(raw, (bytes, bytearray, memoryview)):
            data = bytes(raw)
            break
        last_err = f"unexpected vget payload type {type(raw)!r}"
    if data is None:
        raise RuntimeError(last_err or "vget /camera/*/lit png failed")
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("cv2.imdecode failed for lit png")
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("cv2.imencode jpg failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def maybe_teleport_and_frame(synapse: DroneNavSynapse) -> dict[str, Any] | None:
    """
    Random teleport from OPENFLY_TELEPORT_SPOTS_JSON, wait, capture one lit frame into synapse.

    Mutates ``synapse.instruction`` (spot instruction_preview), ``synapse.frame_jpeg_b64``,
    and refreshes ``synapse.synthetic_context_json`` flags (single-step policy, teleport meta).

    Returns extra dict merged into scoreboard ``synthetic_context`` or None if skipped / failed.
    """
    if not _env_bool("OPENFLY_SYNTHETIC_UE_ENABLED", False):
        return None
    spots = _load_spots()
    if not spots:
        return None
    spot = random.choice(spots)
    idx = int(spot.get("index", spots.index(spot)))
    preview = str(spot.get("instruction_preview") or "").strip()
    title = str(spot.get("title") or spot.get("folder") or f"spot_{idx}")

    client = None
    try:
        client = _connect_client()
        _set_camera_pose_unrealcv(
            client,
            float(spot["x"]),
            float(spot["y"]),
            float(spot["z"]),
            float(spot.get("pitch_deg", 0.0)),
            float(spot["yaw_rad"]),
            0.0,
        )
        time.sleep(_sleep_after_teleport())
        b64 = _capture_lit_jpeg_b64(client)
    except Exception as e:
        bt.logging.error(f"UE synthetic teleport/capture failed: {e!r}")
        return {"ue_synthetic_ok": False, "ue_synthetic_error": repr(e)}
    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

    if preview:
        synapse.instruction = preview[:8000]
    synapse.frame_jpeg_b64 = b64

    try:
        ctx = json.loads(synapse.synthetic_context_json or "{}")
        if not isinstance(ctx, dict):
            ctx = {}
    except (TypeError, ValueError, json.JSONDecodeError):
        ctx = {}
    ctx.update(
        {
            "teleport_index": idx,
            "teleport_title": title,
            "teleport_folder": str(spot.get("folder") or ""),
            "post_teleport_sleep_sec": _sleep_after_teleport(),
            "ai_mode": "single_step",
            "ai_steps_loop": False,
        }
    )
    synapse.synthetic_context_json = json.dumps(ctx, ensure_ascii=False)

    bt.logging.info(f"UE synthetic: teleported to #{idx} «{title[:64]}», frame attached, ai_mode=single_step")
    return {
        "ue_synthetic_ok": True,
        "teleport_index": idx,
        "teleport_title": title,
        "teleport_folder": str(spot.get("folder") or ""),
        "post_teleport_sleep_sec": _sleep_after_teleport(),
        "ai_mode": "single_step",
        "frame_chars": len(b64),
    }
