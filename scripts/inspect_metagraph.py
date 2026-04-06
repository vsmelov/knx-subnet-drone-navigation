#!/usr/bin/env python3
"""Снимок метаграфа по netuid (incentive, stake, hotkeys)."""

from __future__ import annotations

import argparse
import json

import bittensor as bt
import numpy as np


def _scalar(x, as_int: bool = False) -> float | int:
    a = np.asarray(x).reshape(-1)
    if a.size == 0:
        return 0 if as_int else 0.0
    v = a.flat[0]
    return int(v) if as_int else float(v)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--netuid", type=int, required=True)
    p.add_argument(
        "--chain-endpoint",
        default="ws://127.0.0.1:9944",
        help="С хоста: ws://127.0.0.1:9944; из Docker-сети: ws://subtensor-localnet:9944",
    )
    args = p.parse_args()
    st = bt.Subtensor(network=args.chain_endpoint)
    mg = st.metagraph(args.netuid)
    n = int(np.asarray(mg.n).reshape(-1)[0])
    rows = []
    for uid in range(n):
        ax = mg.axons[uid]
        row = {
            "uid": uid,
            "hotkey": str(mg.hotkeys[uid]),
            "stake": _scalar(mg.S[uid]),
            "incentive": _scalar(mg.I[uid]),
            "dividends": _scalar(mg.D[uid]),
            "ip": str(ax.ip) if ax.ip is not None else "",
            "port": _scalar(ax.port, as_int=True),
        }
        if hasattr(mg, "T"):
            row["trust"] = _scalar(mg.T[uid])
        rows.append(row)
    print(
        json.dumps(
            {"netuid": int(args.netuid), "n": n, "neurons": rows},
            indent=2,
            default=lambda o: o.tolist()
            if hasattr(o, "tolist")
            else int(o)
            if isinstance(o, np.integer)
            else float(o)
            if isinstance(o, np.floating)
            else str(o),
        )
    )


if __name__ == "__main__":
    main()
