"""AI evidence bundle hashing, remark publishing, and control-plane mirroring."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bittensor as bt


EVIDENCE_VERSION = "konnex-ai-evidence-v1"


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_hash(bundle: dict[str, Any]) -> str:
    return "0x" + hashlib.sha256(canonical_json(bundle).encode("utf-8")).hexdigest()


def _safe_response_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"raw": str(raw)[:2000]}
    return obj if isinstance(obj, dict) else {"raw": obj}


def build_drone_evidence_bundle(
    *,
    validator_self: Any,
    synapse: Any,
    synthetic_context: dict[str, Any],
    miner_uids: list[int],
    responses: list[Any],
    scoreboard: dict[str, Any],
    run_dir: Path | None,
) -> tuple[dict[str, Any], str]:
    validator_hotkey = str(validator_self.wallet.hotkey.ss58_address)
    miner_entries: list[dict[str, Any]] = []
    for idx, response in enumerate(responses):
        uid = int(miner_uids[idx]) if idx < len(miner_uids) else None
        miner_entries.append(
            {
                "uid": uid,
                "action_id": getattr(response, "action_id", None),
                "confidence": getattr(response, "confidence", None),
                "miner_error": getattr(response, "miner_error", None),
                "response": _safe_response_json(getattr(response, "miner_response_json", None)),
                "dendrite_status_code": getattr(getattr(response, "dendrite", None), "status_code", None),
            }
        )

    evidence_files: list[str] = []
    if run_dir is not None:
        for name in ("request.json", "frame.png", "miners_replies.json", "scoring.json", "metadata.json"):
            if (run_dir / name).exists():
                evidence_files.append(name)

    bundle = {
        "version": EVIDENCE_VERSION,
        "subnet": "drone-navigation",
        "netuid": int(validator_self.config.netuid),
        "job_id": str(synapse.task_id),
        "miner_uids": [int(uid) for uid in miner_uids],
        "validator_hotkey": validator_hotkey,
        "ai_mode": "openai",
        "model_name": os.environ.get("OPENAI_GPT_POLICY_MODEL", "gpt-4.1"),
        "verifier_mode": "ue_synthetic",
        "fallback_used": False,
        "input_refs": {
            "instruction": str(synapse.instruction),
            "synthetic_context": synthetic_context,
            "has_frame": bool(getattr(synapse, "frame_jpeg_b64", None)),
        },
        "artifact_refs": evidence_files,
        "score": {
            "rewards": scoreboard.get("rewards", []),
            "verification": scoreboard.get("verification", []),
        },
        "verdict": "winner" if any(float(x) > 0 for x in scoreboard.get("rewards", [])) else "no_reward",
        "miners": miner_entries,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    h = evidence_hash(bundle)
    bundle["evidence_hash"] = h
    return bundle, h


def publish_evidence_remark(validator_self: Any, *, evidence_hash_value: str, job_id: str) -> dict[str, Any]:
    if os.environ.get("KONNEX_AI_EVIDENCE_DISABLE_REMARK", "").lower() in ("1", "true", "yes"):
        return {"ok": False, "skipped": True, "error": "remark disabled by KONNEX_AI_EVIDENCE_DISABLE_REMARK"}
    remark = f"konnex-ai-evidence:v1:drone-navigation:{job_id}:{evidence_hash_value}"
    try:
        substrate = validator_self.subtensor.substrate
        call = substrate.compose_call(
            call_module="System",
            call_function="remark",
            call_params={"remark": remark},
        )
        extrinsic = substrate.create_signed_extrinsic(call=call, keypair=getattr(validator_self.wallet, "coldkey", validator_self.wallet.hotkey))
        receipt = substrate.submit_extrinsic(
            extrinsic,
            wait_for_inclusion=False,
            wait_for_finalization=False,
        )
        tx_hash = getattr(receipt, "extrinsic_hash", None) or getattr(extrinsic, "extrinsic_hash", None)
        return {"ok": True, "remark": remark, "extrinsic_hash": str(tx_hash) if tx_hash else None}
    except Exception as exc:
        bt.logging.warning(f"AI evidence remark failed: {type(exc).__name__}: {exc}")
        return {"ok": False, "remark": remark, "error": f"{type(exc).__name__}: {exc}"}


def _post_control_plane(path: str, payload: dict[str, Any]) -> None:
    base = os.environ.get("KONNEX_CONTROL_PLANE_URL", "").rstrip("/")
    token = os.environ.get("KONNEX_INTERNAL_API_TOKEN", "").strip()
    if not base or not token:
        return
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("KONNEX_CONTROL_PLANE_TIMEOUT", "5"))):
            return
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        bt.logging.warning(f"control-plane evidence mirror failed {path}: {exc}")


def mirror_evidence_to_control_plane(
    *,
    validator_self: Any,
    bundle: dict[str, Any],
    evidence_remark: dict[str, Any],
) -> None:
    artifact_id = f"drone-netuid{bundle['netuid']}-{bundle['job_id']}-evidence"
    metadata = {
        **bundle,
        "evidence_extrinsic_hash": evidence_remark.get("extrinsic_hash"),
        "evidence_remark": evidence_remark.get("remark"),
        "evidence_remark_error": evidence_remark.get("error"),
    }
    now = str(bundle["created_at"])
    _post_control_plane(
        "/api/internal/artifacts",
        {
            "artifact_id": artifact_id,
            "subnet": "drone-navigation",
            "artifact_type": "drone-ai-evidence",
            "title": "Drone AI evidence bundle",
            "public_url": None,
            "preview_url": None,
            "storage_key": None,
            "metadata": metadata,
            "created_at": now,
        },
    )
    _post_control_plane(
        "/api/internal/jobs/upsert",
        {
            "job_id": str(bundle["job_id"]),
            "subnet": "drone-navigation",
            "status": "completed",
            "episode_id": str(bundle["job_id"]),
            "payload": {"instruction": bundle["input_refs"]["instruction"], "netuid": bundle["netuid"]},
            "artifact_refs": [artifact_id],
            "transcript_summary": {"ai_metadata": metadata, "latest_verdict": bundle["verdict"]},
            "updated_at": now,
            "created_at": now,
        },
    )
