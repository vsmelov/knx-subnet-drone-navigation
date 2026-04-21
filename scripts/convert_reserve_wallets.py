#!/usr/bin/env python3
"""
Convert ``NN-reserve-NN.wallet.json`` vault exports into a Bittensor ``BT_WALLET_PATH`` tree
(``<coldkey_name>/coldkey``, ``<coldkey_name>/hotkeys/<hotkey_name>``, …).

Each reserve file is one SR25519 mnemonic. This script uses the **same** mnemonic for coldkey
and hotkey (typical for a simple server wallet / localnet). SS58 matches ``accountSs58`` in JSON.

Example (validator = wallet 07, miner = 08)::

  cd xsubnet-template
  export BT_WALLET_PATH="$(pwd)/wallets"
  python scripts/convert_reserve_wallets.py \\
    --validator-json wallets/07-reserve-07.wallet.json \\
    --miner-json wallets/08-reserve-08.wallet.json

Then set in ``.env``::

  VALIDATOR_WALLET_NAME=validator
  VALIDATOR_WALLET_HOTKEY=default
  MINER_WALLET_NAME=miner
  MINER_WALLET_HOTKEY=default
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _phrase_from_wallet_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    phrase = str(data.get("secretPhrase", "")).strip()
    if not phrase:
        raise SystemExit(f"{path}: missing secretPhrase")
    return phrase


def _verify_ss58(phrase: str, expected_ss58: str | None) -> None:
    if not expected_ss58:
        return
    try:
        from substrateinterface import Keypair
        from substrateinterface.keypair import KeypairType
    except ImportError:
        print("warning: pip install substrate-interface to verify accountSs58", file=sys.stderr)
        return
    kp = Keypair.create_from_mnemonic(phrase, crypto_type=KeypairType.SR25519)
    if kp.ss58_address != expected_ss58:
        raise SystemExit(
            f"mnemonic SS58 {kp.ss58_address!r} != JSON accountSs58 {expected_ss58!r}"
        )


def _regen_wallet(
    *,
    wallet_path: Path,
    coldkey_name: str,
    hotkey_name: str,
    mnemonic: str,
    dry_run: bool,
) -> None:
    try:
        from bittensor_wallet import Wallet
    except ImportError as e:
        raise SystemExit(
            "Need bittensor_wallet (install with: pip install 'bittensor>=9.7' or bittensor_wallet)"
        ) from e

    os.environ["BT_WALLET_PATH"] = str(wallet_path)
    if dry_run:
        print(f"dry-run: would regenerate cold+hot for {coldkey_name}/{hotkey_name}")
        return
    w = Wallet(name=coldkey_name, hotkey=hotkey_name, path=str(wallet_path))
    # bittensor_wallet prints the mnemonic to stdout; suppress so it never lands in logs/CI.
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf):
        w.regenerate_coldkey(mnemonic=mnemonic, use_password=False, overwrite=True)
        w.regenerate_hotkey(mnemonic=mnemonic, use_password=False, overwrite=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--wallet-path",
        type=Path,
        default=_ROOT / "wallets",
        help="BT_WALLET_PATH root (default: xsubnet-template/wallets)",
    )
    p.add_argument(
        "--validator-json",
        type=Path,
        default=_ROOT / "wallets" / "07-reserve-07.wallet.json",
        help="Reserve export JSON for the validator keypair",
    )
    p.add_argument(
        "--miner-json",
        type=Path,
        default=_ROOT / "wallets" / "08-reserve-08.wallet.json",
        help="Reserve export JSON for the miner keypair",
    )
    p.add_argument("--validator-name", default="validator", help="Coldkey directory name for validator")
    p.add_argument("--miner-name", default="miner", help="Coldkey directory name for miner")
    p.add_argument("--hotkey", default="default", help="Hotkey file name under hotkeys/")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    wallet_path = args.wallet_path.resolve()
    val_json = args.validator_json.resolve()
    min_json = args.miner_json.resolve()
    for f in (val_json, min_json):
        if not f.is_file():
            raise SystemExit(f"missing file: {f}")

    val_phrase = _phrase_from_wallet_json(val_json)
    min_phrase = _phrase_from_wallet_json(min_json)
    val_ss58 = json.loads(val_json.read_text(encoding="utf-8")).get("accountSs58")
    min_ss58 = json.loads(min_json.read_text(encoding="utf-8")).get("accountSs58")
    _verify_ss58(val_phrase, str(val_ss58) if val_ss58 else None)
    _verify_ss58(min_phrase, str(min_ss58) if min_ss58 else None)

    wallet_path.mkdir(parents=True, exist_ok=True)

    _regen_wallet(
        wallet_path=wallet_path,
        coldkey_name=args.validator_name,
        hotkey_name=args.hotkey,
        mnemonic=val_phrase,
        dry_run=args.dry_run,
    )
    _regen_wallet(
        wallet_path=wallet_path,
        coldkey_name=args.miner_name,
        hotkey_name=args.hotkey,
        mnemonic=min_phrase,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        print(f"Wrote Bittensor wallets under {wallet_path}")
        print(f"  validator: {args.validator_name} / hotkey {args.hotkey}")
        print(f"  miner:     {args.miner_name} / hotkey {args.hotkey}")
    print()
    print("Set in .env (names only):")
    print(f"  VALIDATOR_WALLET_NAME={args.validator_name}")
    print(f"  VALIDATOR_WALLET_HOTKEY={args.hotkey}")
    print(f"  MINER_WALLET_NAME={args.miner_name}")
    print(f"  MINER_WALLET_HOTKEY={args.hotkey}")
    print()
    print(f"export BT_WALLET_PATH={wallet_path}")


if __name__ == "__main__":
    main()
