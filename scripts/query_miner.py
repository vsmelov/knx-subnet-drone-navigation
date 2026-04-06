#!/usr/bin/env python3
"""
Один запрос MathSynapse к майнеру по UID (нужен зарегистрированный coldkey/hotkey для подписи dendrite).

Запуск из корня репо, в той же Docker-сети, что и localnet (подставьте NETUID и кошелёк):

  docker compose -f docker-compose.subnet-math.yml --env-file .env.subnet-math run --rm -T \\
    --entrypoint python math-miner scripts/query_miner.py \\
    --netuid 2 --wallet-name math-val --miner-uid 1 \\
    --subtensor.chain_endpoint ws://subtensor-localnet:9944 \\
    --operand_a 6 --operand_b 7 --op "*"
"""

from __future__ import annotations

import argparse
import asyncio

import bittensor as bt

from template.protocol import MathSynapse


async def _run(args: argparse.Namespace) -> None:
    wallet = bt.Wallet(name=args.wallet_name, hotkey=args.hotkey)
    subtensor = bt.Subtensor(network=args.chain)
    mg = subtensor.metagraph(args.netuid)
    if args.miner_uid < 0 or args.miner_uid >= mg.n:
        raise SystemExit(f"miner-uid out of range 0..{mg.n - 1}")
    axon = mg.axons[args.miner_uid]
    dendrite = bt.Dendrite(wallet)
    synapse = MathSynapse(
        operand_a=args.operand_a, operand_b=args.operand_b, op=args.op
    )
    out = await dendrite(
        [axon], synapse=synapse, deserialize=True, timeout=args.timeout
    )
    print("axon:", axon)
    print("response:", out[0] if out else out)


def main() -> None:
    p = argparse.ArgumentParser(description="Single MathSynapse query to miner UID")
    p.add_argument("--netuid", type=int, required=True)
    p.add_argument("--wallet-name", required=True, help="Coldkey name (must be registered)")
    p.add_argument("--hotkey", default="default")
    p.add_argument(
        "--subtensor.chain_endpoint",
        dest="chain",
        default="ws://127.0.0.1:9944",
        help="Inside Docker use ws://subtensor-localnet:9944",
    )
    p.add_argument("--miner-uid", type=int, required=True)
    p.add_argument("--operand_a", type=int, default=6)
    p.add_argument("--operand_b", type=int, default=7)
    p.add_argument("--op", default="*")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
