#!/usr/bin/env bash
# Install the XYZ CloudWatch job-log discovery service on a Linux EC2 host.

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

AGENT_CTL="/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl"
REFRESH_SOURCE="$SCRIPT_DIR/refresh-xyz-cwlogs.sh"
ENV_SOURCE="$SCRIPT_DIR/xyz-cwlogs-refresh.env"
SERVICE_SOURCE="$SCRIPT_DIR/xyz-cwlogs-refresh.service"
TIMER_SOURCE="$SCRIPT_DIR/xyz-cwlogs-refresh.timer"

REFRESH_TARGET="/usr/local/sbin/refresh-xyz-cwlogs.sh"
ENV_TARGET="/etc/default/xyz-cwlogs-refresh"
SERVICE_TARGET="/etc/systemd/system/xyz-cwlogs-refresh.service"
TIMER_TARGET="/etc/systemd/system/xyz-cwlogs-refresh.timer"

log() {
    printf 'install-cloudwatch-job-logs: %s\n' "$*"
}

fatal() {
    printf 'install-cloudwatch-job-logs: ERROR: %s\n' "$*" >&2
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fatal "Run this installer as root, for example: sudo bash install.sh"

command -v systemctl >/dev/null 2>&1 || fatal "systemctl is not available on this host"
[[ -x "$AGENT_CTL" ]] || fatal "Amazon CloudWatch Agent is not installed at $AGENT_CTL"

for source_file in \
    "$REFRESH_SOURCE" \
    "$ENV_SOURCE" \
    "$SERVICE_SOURCE" \
    "$TIMER_SOURCE"; do
    [[ -f "$source_file" ]] || fatal "Required repository file is missing: $source_file"
done

log "Installing refresh script to $REFRESH_TARGET"
install -D -m 0755 "$REFRESH_SOURCE" "$REFRESH_TARGET"

if [[ -e "$ENV_TARGET" ]]; then
    log "Keeping existing settings file: $ENV_TARGET"
    log "Compare it with $ENV_SOURCE if new settings are introduced later."
else
    log "Installing default settings to $ENV_TARGET"
    install -D -m 0644 "$ENV_SOURCE" "$ENV_TARGET"
fi

log "Installing systemd service and timer"
install -D -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"
install -D -m 0644 "$TIMER_SOURCE" "$TIMER_TARGET"

log "Reloading systemd"
systemctl daemon-reload

log "Enabling discovery timer"
systemctl enable --now xyz-cwlogs-refresh.timer

log "Running one immediate discovery pass"
if systemctl start xyz-cwlogs-refresh.service; then
    log "Initial refresh completed successfully."
else
    log "Initial refresh failed. Inspect: journalctl -u xyz-cwlogs-refresh.service -n 100 --no-pager"
    exit 1
fi

log "Installation complete."
log "Timer status: systemctl status xyz-cwlogs-refresh.timer"
log "Service logs: journalctl -u xyz-cwlogs-refresh.service"
