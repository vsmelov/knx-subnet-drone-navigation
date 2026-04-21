# Docker Compose: Miner and Validator (with UE)

This branch adds two compose entrypoints:

- `docker-compose.miner.yml` - standalone miner node.
- `docker-compose.validator.yml` - validator node plus `openfly-ue` sidecar.

The validator stack uses `network_mode: service:openfly-ue` so validator traffic can reliably access
UnrealCV on `127.0.0.1` and UDS socket under shared `/tmp`.

`openfly-ue` and `subnet-validator` mount the same **Docker named volume** (`openfly_ue_validator_tmp`) at `/tmp`, so
Xvfb lock files and the UnrealCV Unix socket are **not** mixed with the host `logs/` tree (stale `.X*-lock` files
there used to break Xvfb on unrelated display numbers).

## 1) Prepare environment

From `xsubnet-template` root:

```bash
cp .env.example .env
mkdir -p wallets data logs/ue-dashboard logs
git submodule update --init --recursive
```

`./data/teleport_spots.json` is mounted read-only into the validator for random UE teleports before each synthetic round (`OPENFLY_TELEPORT_SPOTS_JSON`). Synthetic interval: `OPENFLY_VALIDATOR_FORWARD_SLEEP` → `--neuron.forward_sleep` (default 20 minutes in code / `.env.example`).

Debug dumps: set **`VALIDATOR_SYNTHETIC_DEBUG=1`** to write each round under **`./logs/VALIDATOR_SYNTHETIC_DEBUG/<UTC-datetime>/`**: `request.json`, `frame.png` (when UE attached a JPEG frame), `miners_replies.json`, `scoring.json`, `metadata.json`. Override directory with **`VALIDATOR_SYNTHETIC_DEBUG_DIR`** (container path, default `/app/logs/VALIDATOR_SYNTHETIC_DEBUG`).

Bittensor keys live in **`./wallets/`** (gitignored); compose mounts that tree to `/root/.bittensor/wallets`. Populate it with `export BT_WALLET_PATH="$PWD/wallets"` and `btcli wallet …`, or copy from an existing `~/.bittensor/wallets` layout.

UnrealCV: **`OPENFLY_UNREALCV_PORT`** is internal to the UE/validator shared network namespace. In this subnet compose we do not publish UnrealCV to host; only validator axon is exposed.

Asset bootstrap is now built into `docker-compose.validator.yml` via `assets-init` service:

- Model weights are downloaded to `./models/openfly-agent-7b` (default HF repo `IPEC-COMMUNITY/openfly-agent-7b`).
- UE env is downloaded either:
  - from `OPENFLY_UE_ARCHIVE_URL` (preferred when you have a stable internal archive), or
  - from HF dataset fallback (`IPEC-COMMUNITY/OpenFly_DataGen`, subdir `ue/env_ue_smallcity`).

You can disable auto-download with `OPENFLY_ASSET_AUTO_DOWNLOAD=0` and manage assets manually.
`subnet-validator` now also waits for `assets-init` completion and `openfly-ue` health, so validator start
does not race model/env bootstrap.

## 2) Start miner

The miner image is **CUDA + OpenFly train deps** (`docker/subnet-miner/Dockerfile`). You need **NVIDIA Container Toolkit**, `./OpenFly-Platform` (submodule), and `./models/openfly-agent-7b` (or set `OPENFLY_MODEL` to an HF id). HF cache dirs under `./logs/miner-*-cache` are optional but recommended (see `docker-compose.miner.yml`).

```bash
docker compose -f docker-compose.miner.yml up -d --build
docker compose -f docker-compose.miner.yml ps
```

## 3) Start validator with UE sidecar

```bash
docker compose -f docker-compose.validator.yml up -d --build
docker compose -f docker-compose.validator.yml ps
docker compose -f docker-compose.validator.yml logs assets-init --tail 120
docker compose -f docker-compose.validator.yml logs openfly-ue --tail 80
docker compose -f docker-compose.validator.yml logs subnet-validator --tail 80
```

## Synthetic round frequency (on-chain validator)

Between each synthetic query round the validator sleeps **`--neuron.forward_sleep`** seconds (default **3600**).
Configure on the `neurons/validator.py` command line, e.g. ``--neuron.forward_sleep 60``.

Each miner query uses dendrite **`--neuron.timeout`** seconds (default **10**); this is now passed explicitly to ``dendrite(...)``.

## Offchain smoke (validator → miner, no weights)

To check that metagraph axons answer with the same `DroneNavSynapse` shape as production forward (without running the full validator loop or setting weights):

```bash
cd xsubnet-template
PYTHONPATH=. python scripts/offchain_validator_smoke.py \
  --netuid 1 --miner-uids 0 --rounds 2 --sleep 1 --timeout 30 \
  --wallet-name validator --wallet-hotkey default \
  --subtensor.chain_endpoint ws://127.0.0.1:9944
```

Optional: ``--tag-offchain`` sets `synthetic_context_json.offchain_smoke=true` so a miner can log or branch on smoke traffic.

## Notes

- Current validator code does not yet execute full drone-navigation scoring. This compose is infrastructure-first:
  it ensures validator and UE are co-deployed and wired for synthetic request workflows.
- If UE is killed uncleanly and Xvfb lock persists, entrypoint removes stale `/tmp/.X99-lock` automatically.
- On single-GPU hosts, tune `NVIDIA_VISIBLE_DEVICES` per service if you split roles across machines.
- For private HF assets set `HF_TOKEN` in `.env`.
