#!/usr/bin/env bash
set -euo pipefail

OFP="${OPENFLY_PLATFORM_ROOT:-/app/OpenFly-Platform}"
UE_ENV="${OPENFLY_UE_ENV_NAME:-env_ue_smallcity}"
UE_DIR="${OFP}/envs/ue/${UE_ENV}"
INI="${UE_DIR}/City_UE52/Binaries/Linux/unrealcv.ini"
PORT="${OPENFLY_UNREALCV_PORT:-9030}"

if [[ ! -d "$UE_DIR" ]]; then
  echo "entrypoint-ue: нет каталога сцены: $UE_DIR (смонтируйте OpenFly-Platform)" >&2
  exit 1
fi

if [[ -f "$INI" ]]; then
  if grep -qE '^[Pp][Oo][Rr][Tt]=' "$INI"; then
    sed -i "s/^[Pp][Oo][Rr][Tt]=.*/Port=${PORT}/" "$INI"
  else
    printf '\nPort=%s\n' "${PORT}" >>"$INI"
  fi
  echo "entrypoint-ue: UnrealCV Port=${PORT} в $(basename "$INI")"
fi

if [[ "${OPENFLY_UE_ENSURE_BEST:-1}" =~ ^(1|true|yes|on)$ ]]; then
  _best="${UE_DIR}/City_UE52/Saved/Config/Linux/GameUserSettings_best.ini"
  _game="${UE_DIR}/City_UE52/Saved/Config/Linux/GameUserSettings.ini"
  if [[ -f "$_best" ]]; then
    cp -f "$_best" "$_game"
    echo "entrypoint-ue: GameUserSettings_best.ini -> GameUserSettings.ini"
  fi
fi

# Виртуальный дисплей только внутри контейнера — без TCP к host и без сканирования :100–:310.
export DISPLAY="${OPENFLY_UE_XVFB_DISPLAY:-:99}"
# SDL/Vulkan в контейнере без login-сессии ругаются и иногда падают без runtime dir.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/openfly-ue-xdg}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"

# Shared /tmp (Docker named volume with validator, or host bind-mount): remove stale X lock for this display.
rm -f "/tmp/.X11-unix/X${DISPLAY#:}" "/tmp/.X${DISPLAY#:}-lock"
Xvfb "${DISPLAY}" -screen 0 1920x1080x24 -ac +extension RANDR +render -noreset &>/tmp/openfly-ue-xvfb.log &
XVFB_PID=$!
sleep "${OPENFLY_UE_XVFB_READY_SEC:-2}"
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo "entrypoint-ue: Xvfb не поднялся на ${DISPLAY}" >&2
  tail -80 /tmp/openfly-ue-xvfb.log 2>/dev/null >&2 || true
  exit 1
fi

export UE_PROJECT_ROOT="${UE_DIR}"
cd "$UE_DIR"

# Общий bind-mount /tmp с бэкендом (UnrealCV UDS); не оставлять сокет от прошлого запуска.
rm -f "/tmp/unrealcv_${PORT}.socket"

# Тот же файл, что OPENFLY_UE_LOGFILE у Python (attach): stdout/stderr City Sample → общий bind-mount.
if [[ -n "${OPENFLY_UE_LOGFILE:-}" ]]; then
  mkdir -p "$(dirname "${OPENFLY_UE_LOGFILE}")"
  touch "${OPENFLY_UE_LOGFILE}" || true
  exec > >(tee -a "${OPENFLY_UE_LOGFILE}") 2>&1
  echo "entrypoint-ue: tee → ${OPENFLY_UE_LOGFILE}"
fi

# Кастомные аргументы — через CitySample.sh.
if [[ -n "${OPENFLY_UE_BINARY_ARGS:-}" ]]; then
  read -r -a _extra <<<"${OPENFLY_UE_BINARY_ARGS}"
  echo "entrypoint-ue: DISPLAY=${DISPLAY}  CitySample.sh ${_extra[*]}"
  exec bash CitySample.sh "${_extra[@]}"
fi

echo "entrypoint-ue: DISPLAY=${DISPLAY}  CitySample.sh -RenderOffScreen …"
exec bash CitySample.sh -RenderOffScreen -NoSound -NoVSync -log
