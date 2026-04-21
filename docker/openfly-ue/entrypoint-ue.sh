#!/usr/bin/env bash
set -euo pipefail

OFP="${OPENFLY_PLATFORM_ROOT:-/app/OpenFly-Platform}"
UE_ENV="${OPENFLY_UE_ENV_NAME:-env_ue_smallcity}"
UE_DIR="${OFP}/envs/ue/${UE_ENV}"
INI="${UE_DIR}/City_UE52/Binaries/Linux/unrealcv.ini"
PORT="${OPENFLY_UNREALCV_PORT:-9030}"

if [[ ! -d "$UE_DIR" ]]; then
  echo "entrypoint-ue: missing scene dir $UE_DIR" >&2
  exit 1
fi

# Avoid sed -i temp files next to CitySample (bind-mount perms / ro dirs); write via /tmp.
if [[ -f "$INI" ]]; then
  _ini_tmp="$(mktemp /tmp/openfly-ue-unrealcv-ini.XXXXXX)"
  if grep -qE '^[Pp][Oo][Rr][Tt]=' "$INI"; then
    sed "s/^[Pp][Oo][Rr][Tt]=.*/Port=${PORT}/" "$INI" >"$_ini_tmp"
  else
    { cat "$INI"; printf '\nPort=%s\n' "${PORT}"; } >"$_ini_tmp"
  fi
  cat "$_ini_tmp" >"$INI"
  rm -f "$_ini_tmp"
fi

export DISPLAY="${OPENFLY_UE_XVFB_DISPLAY:-:99}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/openfly-ue-xdg}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"

rm -f "/tmp/.X11-unix/X${DISPLAY#:}" "/tmp/.X${DISPLAY#:}-lock"
Xvfb "${DISPLAY}" -screen 0 1920x1080x24 -ac +extension RANDR +render -noreset >/tmp/openfly-ue-xvfb.log 2>&1 &
XVFB_PID=$!
sleep "${OPENFLY_UE_XVFB_READY_SEC:-2}"
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo "entrypoint-ue: Xvfb failed on ${DISPLAY}" >&2
  exit 1
fi

cd "$UE_DIR"
rm -f "/tmp/unrealcv_${PORT}.socket"

if [[ -n "${OPENFLY_UE_LOGFILE:-}" ]]; then
  mkdir -p "$(dirname "${OPENFLY_UE_LOGFILE}")"
  touch "${OPENFLY_UE_LOGFILE}" || true
  exec > >(tee -a "${OPENFLY_UE_LOGFILE}") 2>&1
fi

if [[ -n "${OPENFLY_UE_BINARY_ARGS:-}" ]]; then
  read -r -a _extra <<<"${OPENFLY_UE_BINARY_ARGS}"
  exec bash CitySample.sh "${_extra[@]}"
fi

exec bash CitySample.sh -RenderOffScreen -NoSound -NoVSync -log
