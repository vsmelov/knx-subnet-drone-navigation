"""
Один проход dendrite + MathSynapse по нескольким UID и те же reward-правила, что у template validator.
Запуск из образа subnet-math (PYTHONPATH включает /app); версия SDK — см. requirements.txt (9.7.0).
"""

from __future__ import annotations

import operator
import random
import time
from typing import Any, List, Optional

import bittensor as bt

from template.protocol import ALLOWED_OPS, MathSynapse
from template.validator.reward import get_rewards

_OPS = {"+": operator.add, "-": operator.sub, "*": operator.mul}


class _RewardLogCtx:
    """Минимальный self для get_rewards (там нужен только bt.logging на warning)."""


def _expected_value(operand_a: int, operand_b: int, op: str) -> float:
    if op not in _OPS:
        raise ValueError(f"op must be one of {list(_OPS)}")
    return float(_OPS[op](operand_a, operand_b))


def _pick_miner_uids(
    mg: bt.metagraph,
    miner_uids: Optional[List[int]],
    sample_size: int,
) -> List[int]:
    n = int(mg.n)
    if miner_uids is not None and len(miner_uids) > 0:
        uids = [int(u) for u in miner_uids if 0 <= int(u) < n]
        if not uids:
            raise ValueError("miner_uids empty or out of metagraph range")
        return uids
    k = max(1, min(int(sample_size), n))
    candidates = [
        u
        for u in range(n)
        if mg.axons[u].is_serving and not bool(mg.validator_permit[u])
    ]
    if len(candidates) < k:
        candidates = [u for u in range(n) if mg.axons[u].is_serving]
    if len(candidates) < k:
        candidates = list(range(n))
    k = min(k, len(candidates))
    return random.sample(candidates, k)


def _extract_float_response(item: Any) -> Optional[float]:
    if item is None:
        return None
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return float(item)
    if hasattr(item, "result"):
        r = getattr(item, "result")
        if r is None:
            return None
        try:
            return float(r)
        except (TypeError, ValueError):
            return None
    return None


def _dendrite_meta(synapse: Any) -> Any:
    d = getattr(synapse, "dendrite", None)
    if d is None:
        return None
    meta: dict = {}
    for attr in ("status_code", "status_message", "process_time", "ip", "port"):
        if hasattr(d, attr):
            v = getattr(d, attr)
            try:
                meta[attr] = v
            except Exception:
                meta[attr] = str(v)
    return meta if meta else str(d)


def _axon_meta(mg: bt.metagraph, uid: int) -> dict:
    ax = mg.axons[uid]
    hk = getattr(ax, "hotkey", None)
    return {
        "ip": getattr(ax, "ip", None),
        "port": getattr(ax, "port", None),
        "is_serving": getattr(ax, "is_serving", None),
        "hotkey": str(hk) if hk is not None else None,
    }


def _synapse_payload(item: Any) -> Any:
    if item is None:
        return None
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return {"deserialized_only": float(item)}
    out: dict = {"result": getattr(item, "result", None)}
    for k in ("operand_a", "operand_b", "op"):
        if hasattr(item, k):
            out[k] = getattr(item, k)
    out["dendrite"] = _dendrite_meta(item)
    return out


def _hotkey_at(mg: bt.metagraph, uid: int) -> Optional[str]:
    try:
        h = mg.hotkeys[uid]
        return str(h)
    except Exception:
        return None


async def run_math_probe(
    *,
    netuid: int,
    chain_endpoint: str,
    wallet_name: str,
    hotkey: str = "default",
    miner_uids: Optional[List[int]] = None,
    sample_size: int = 4,
    operand_a: int = 6,
    operand_b: int = 7,
    op: str = "*",
    timeout: float = 30.0,
) -> dict:
    t0 = time.perf_counter()
    if op not in ALLOWED_OPS:
        return {"ok": False, "error": f"op must be one of {ALLOWED_OPS}"}

    wallet = bt.Wallet(name=wallet_name, hotkey=hotkey)
    subtensor = bt.Subtensor(network=chain_endpoint)
    mg = subtensor.metagraph(netuid)

    uids_list = _pick_miner_uids(mg, miner_uids, sample_size)
    expected = _expected_value(operand_a, operand_b, op)
    synapse = MathSynapse(operand_a=operand_a, operand_b=operand_b, op=op)
    axons = [mg.axons[u] for u in uids_list]

    dendrite = bt.Dendrite(wallet)
    t_call = time.perf_counter()
    raw_out = None
    used_deserialize_true = False
    try:
        raw_out = await dendrite(
            axons,
            synapse=synapse,
            deserialize=False,
            timeout=timeout,
        )
    except TypeError:
        raw_out = await dendrite(
            axons,
            synapse=synapse,
            deserialize=True,
            timeout=timeout,
        )
        used_deserialize_true = True
    t_after = time.perf_counter()

    if raw_out is None:
        raw_list: List[Any] = []
    elif isinstance(raw_out, (list, tuple)):
        raw_list = list(raw_out)
    else:
        raw_list = [raw_out]

    responses_float: List[Optional[float]] = []
    miners: List[dict] = []
    for i, uid in enumerate(uids_list):
        item = raw_list[i] if i < len(raw_list) else None
        fv = _extract_float_response(item)
        responses_float.append(fv)
        err_abs = abs(fv - expected) if fv is not None else None
        miners.append(
            {
                "uid": int(uid),
                "hotkey_ss58": _hotkey_at(mg, uid),
                "axon": _axon_meta(mg, uid),
                "response_float": fv,
                "synapse": _synapse_payload(item),
                "abs_error": err_abs,
            }
        )

    rewards = get_rewards(_RewardLogCtx(), expected=expected, responses=responses_float)
    rew_list = [float(x) for x in rewards.tolist()]
    for i, r in enumerate(rew_list):
        if i < len(miners):
            miners[i]["reward_share"] = r

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    call_ms = int((t_after - t_call) * 1000)

    return {
        "ok": True,
        "protocol": "subnet-math MathSynapse",
        "bittensor_sdk_pinned": "9.7.0 (see subnet-math/requirements.txt in repo)",
        "netuid": netuid,
        "chain_endpoint": chain_endpoint,
        "wallet_coldkey": wallet_name,
        "dendrite_deserialize_flag": not used_deserialize_true,
        "request": {
            "operand_a": operand_a,
            "operand_b": operand_b,
            "op": op,
            "expected": expected,
        },
        "miner_uids_queried": uids_list,
        "miners": miners,
        "rewards": rew_list,
        "timing_ms": {"total": elapsed_ms, "dendrite_call": call_ms},
    }
