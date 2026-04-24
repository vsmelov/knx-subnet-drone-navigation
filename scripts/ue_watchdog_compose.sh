#!/bin/sh
set -eu

STATE_FILE="${STATE_FILE:-/tmp/ue_watchdog_last_restart}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-xsubnet-template}"
UE_TIMEOUT_WINDOW_SEC="${UE_TIMEOUT_WINDOW_SEC:-900}"
UE_TIMEOUT_THRESHOLD="${UE_TIMEOUT_THRESHOLD:-3}"
RESTART_COOLDOWN_SEC="${RESTART_COOLDOWN_SEC:-900}"
WATCHDOG_INTERVAL_SEC="${WATCHDOG_INTERVAL_SEC:-30}"
OPENFLY_HEALTH_URL="${OPENFLY_HEALTH_URL:-}"
OPENFLY_HEALTH_TIMEOUT_SEC="${OPENFLY_HEALTH_TIMEOUT_SEC:-3}"
OPENFLY_NOT_READY_GRACE_SEC="${OPENFLY_NOT_READY_GRACE_SEC:-180}"
OPENFLY_NOT_READY_FILE="${OPENFLY_NOT_READY_FILE:-${STATE_FILE}.openfly_not_ready_since}"
OPENFLY_BACKEND_CONTAINER="${OPENFLY_BACKEND_CONTAINER:-konnex-openfly-dashboard}"
OPENFLY_BACKEND_STATE_FILE="${OPENFLY_BACKEND_STATE_FILE:-${STATE_FILE}.openfly_backend_restart}"
OPENFLY_BACKEND_UNAVAILABLE_GRACE_SEC="${OPENFLY_BACKEND_UNAVAILABLE_GRACE_SEC:-60}"
OPENFLY_BACKEND_RESTART_COOLDOWN_SEC="${OPENFLY_BACKEND_RESTART_COOLDOWN_SEC:-180}"

echo "[ue-watchdog] start project=${COMPOSE_PROJECT_NAME} interval_s=${WATCHDOG_INTERVAL_SEC} timeout_window_s=${UE_TIMEOUT_WINDOW_SEC} timeout_threshold=${UE_TIMEOUT_THRESHOLD} restart_cooldown_s=${RESTART_COOLDOWN_SEC} openfly_health_url=${OPENFLY_HEALTH_URL:-disabled} openfly_not_ready_grace_s=${OPENFLY_NOT_READY_GRACE_SEC} openfly_backend_container=${OPENFLY_BACKEND_CONTAINER} openfly_backend_unavailable_grace_s=${OPENFLY_BACKEND_UNAVAILABLE_GRACE_SEC} openfly_backend_restart_cooldown_s=${OPENFLY_BACKEND_RESTART_COOLDOWN_SEC} state_file=${STATE_FILE}"

read_openfly_health() {
  if [ -z "$OPENFLY_HEALTH_URL" ]; then
    OPENFLY_READY_STATUS="disabled"
    OPENFLY_NOT_READY_FOR=0
    return 0
  fi

  body="$(wget -q -T "$OPENFLY_HEALTH_TIMEOUT_SEC" -O - "$OPENFLY_HEALTH_URL" 2>/dev/null || true)"
  if echo "$body" | grep -q '"ue_ready"[[:space:]]*:[[:space:]]*true'; then
    OPENFLY_READY_STATUS="ready"
    OPENFLY_NOT_READY_FOR=0
    rm -f "$OPENFLY_NOT_READY_FILE" 2>/dev/null || true
    return 0
  fi

  if [ -n "$body" ]; then
    OPENFLY_READY_STATUS="not_ready"
  else
    OPENFLY_READY_STATUS="unavailable"
  fi

  not_ready_since=""
  if [ -f "$OPENFLY_NOT_READY_FILE" ]; then
    not_ready_since="$(cat "$OPENFLY_NOT_READY_FILE" 2>/dev/null || true)"
  fi
  case "$not_ready_since" in
    ''|*[!0-9]*)
      not_ready_since="$now"
      echo "$not_ready_since" > "$OPENFLY_NOT_READY_FILE"
      ;;
  esac
  OPENFLY_NOT_READY_FOR=$((now - not_ready_since))
}

while true; do
  now="$(date +%s)"
  last=0
  if [ -f "$STATE_FILE" ]; then
    last="$(cat "$STATE_FILE" 2>/dev/null || echo 0)"
  fi
  backend_last=0
  if [ -f "$OPENFLY_BACKEND_STATE_FILE" ]; then
    backend_last="$(cat "$OPENFLY_BACKEND_STATE_FILE" 2>/dev/null || echo 0)"
  fi

  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${COMPOSE_PROJECT_NAME}-openfly-ue-1" 2>/dev/null || echo unknown)"
  timeouts="$(docker logs --since "${UE_TIMEOUT_WINDOW_SEC}s" "${COMPOSE_PROJECT_NAME}-subnet-validator-1" 2>&1 | grep -c "UE synthetic teleport/capture timed out after" || true)"
  [ -n "$timeouts" ] || timeouts=0
  read_openfly_health

  reason=""
  backend_reason=""
  if [ "$health" = "unhealthy" ]; then
    reason="ue_unhealthy"
  elif [ "$timeouts" -ge "$UE_TIMEOUT_THRESHOLD" ]; then
    reason="validator_timeouts_${timeouts}"
  elif [ "$OPENFLY_READY_STATUS" = "unavailable" ] && [ "$OPENFLY_NOT_READY_FOR" -ge "$OPENFLY_BACKEND_UNAVAILABLE_GRACE_SEC" ]; then
    backend_reason="openfly_backend_unavailable_${OPENFLY_NOT_READY_FOR}s"
  elif [ "$OPENFLY_READY_STATUS" != "disabled" ] && [ "$OPENFLY_READY_STATUS" != "ready" ] && [ "$OPENFLY_NOT_READY_FOR" -ge "$OPENFLY_NOT_READY_GRACE_SEC" ]; then
    reason="openfly_ue_${OPENFLY_READY_STATUS}_${OPENFLY_NOT_READY_FOR}s"
  fi

  cool_elapsed=$((now - last))
  if [ "$last" = "0" ] || [ -z "$last" ]; then
    cooldown_left_s=0
  elif [ "$cool_elapsed" -ge "$RESTART_COOLDOWN_SEC" ]; then
    cooldown_left_s=0
  else
    cooldown_left_s=$((RESTART_COOLDOWN_SEC - cool_elapsed))
  fi
  backend_cool_elapsed=$((now - backend_last))
  if [ "$backend_last" = "0" ] || [ -z "$backend_last" ]; then
    backend_cooldown_left_s=0
  elif [ "$backend_cool_elapsed" -ge "$OPENFLY_BACKEND_RESTART_COOLDOWN_SEC" ]; then
    backend_cooldown_left_s=0
  else
    backend_cooldown_left_s=$((OPENFLY_BACKEND_RESTART_COOLDOWN_SEC - backend_cool_elapsed))
  fi

  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  pending="${backend_reason:-${reason:-none}}"
  echo "[ue-watchdog] ${ts} tick openfly_ue_health=${health} openfly_ready=${OPENFLY_READY_STATUS} openfly_not_ready_for_s=${OPENFLY_NOT_READY_FOR} validator_timeouts=${timeouts}/${UE_TIMEOUT_THRESHOLD} (last_${UE_TIMEOUT_WINDOW_SEC}s) pending_reason=${pending} cooldown_left_s=${cooldown_left_s} backend_cooldown_left_s=${backend_cooldown_left_s} next_sleep_s=${WATCHDOG_INTERVAL_SEC}"

  if [ -n "$backend_reason" ] && [ $((now - backend_last)) -ge "$OPENFLY_BACKEND_RESTART_COOLDOWN_SEC" ]; then
    echo "[ue-watchdog] trigger=$backend_reason restarting openfly backend container ${OPENFLY_BACKEND_CONTAINER}"
    docker restart "$OPENFLY_BACKEND_CONTAINER"
    rm -f "$OPENFLY_NOT_READY_FILE" 2>/dev/null || true
    echo "$now" > "$OPENFLY_BACKEND_STATE_FILE"
  elif [ -n "$backend_reason" ]; then
    echo "[ue-watchdog] pending_reason=$backend_reason but backend restart cooldown: ${backend_cooldown_left_s}s left"
  elif [ -n "$reason" ] && [ $((now - last)) -ge "$RESTART_COOLDOWN_SEC" ]; then
    echo "[ue-watchdog] trigger=$reason restarting openfly-ue and subnet-validator"
    docker compose -f /workspace/docker-compose.validator.yml up -d --force-recreate openfly-ue
    docker compose -f /workspace/docker-compose.validator.yml up -d --force-recreate subnet-validator
    rm -f "$OPENFLY_NOT_READY_FILE" 2>/dev/null || true
    echo "$now" > "$STATE_FILE"
  elif [ -n "$reason" ]; then
    echo "[ue-watchdog] pending_reason=$reason but restart cooldown: ${cooldown_left_s}s left"
  fi

  sleep "$WATCHDOG_INTERVAL_SEC"
done
