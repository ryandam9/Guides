#!/usr/bin/env bash
#
# Discover /app/xyz/log job files and maintain a CloudWatch Agent
# configuration fragment with one stream per job / EC2 instance / log type.
#
# Stream format:
#   <job-id>/{instance_id}/main
#   <job-id>/{instance_id}/def
#   <job-id>/{instance_id}/dtf
#
# This script is designed to run repeatedly from systemd. It only calls
# amazon-cloudwatch-agent-ctl when the generated configuration changes,
# unless --force is supplied.

set -euo pipefail
IFS=$'\n\t'

PROGRAM_NAME="${0##*/}"

DEFAULT_SETTINGS_FILE="/etc/default/xyz-cwlogs-refresh"
SETTINGS_FILE="${XYZ_CWLOGS_SETTINGS_FILE:-$DEFAULT_SETTINGS_FILE}"

# Load host-specific settings first. Explicit environment variables may be
# supplied by tests/deployment wrappers by using a custom SETTINGS_FILE.
if [[ -r "$SETTINGS_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$SETTINGS_FILE"
fi

LOG_DIR="${LOG_DIR:-/app/xyz/log}"
LOG_GROUP="${LOG_GROUP:-/app/xyz/jobs}"
MAX_FILE_AGE_MINUTES="${MAX_FILE_AGE_MINUTES:-0}"

CW_AGENT_CTL="${CW_AGENT_CTL:-/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl}"
CW_AGENT_CONFIG_DIR="${CW_AGENT_CONFIG_DIR:-/opt/aws/amazon-cloudwatch-agent/etc}"
GENERATED_CONFIG_NAME="${GENERATED_CONFIG_NAME:-xyz-job-logs.json}"
GENERATED_CONFIG_FILE="${GENERATED_CONFIG_FILE:-${CW_AGENT_CONFIG_DIR}/${GENERATED_CONFIG_NAME}}"
LOCK_DIR="${LOCK_DIR:-/run/xyz-cwlogs-refresh.lock}"

DRY_RUN=false
FORCE=false

log() {
    printf '%s: %s\n' "$PROGRAM_NAME" "$*"
}

warn() {
    printf '%s: WARNING: %s\n' "$PROGRAM_NAME" "$*" >&2
}

fatal() {
    printf '%s: ERROR: %s\n' "$PROGRAM_NAME" "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: refresh-xyz-cwlogs.sh [--dry-run] [--force] [--help]

Options:
  --dry-run   Generate and print the configuration, but do not install it or
              call CloudWatch Agent.
  --force     Apply the generated fragment even when it is byte-for-byte
              identical to the currently installed fragment.
  --help      Show this help.
EOF
}

while (($# > 0)); do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --force)
            FORCE=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fatal "Unknown argument: $1"
            ;;
    esac
    shift
done

is_non_negative_integer() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

json_escape() {
    # Escape a shell string for a JSON string value. Newlines/tabs are not
    # expected in configured paths, but handling them here keeps generation
    # deterministic and valid.
    local value="$1"
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/\\r}
    value=${value//$'\t'/\\t}
    printf '%s' "$value"
}

release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}

acquire_lock() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        log "Another refresh is already running; exiting."
        exit 0
    fi
    trap release_lock EXIT INT TERM HUP
}

validate_environment() {
    [[ -d "$LOG_DIR" ]] || fatal "Log directory does not exist: $LOG_DIR"

    is_non_negative_integer "$MAX_FILE_AGE_MINUTES" \
        || fatal "MAX_FILE_AGE_MINUTES must be a non-negative integer: $MAX_FILE_AGE_MINUTES"

    if [[ "$DRY_RUN" == false ]]; then
        [[ ${EUID:-$(id -u)} -eq 0 ]] \
            || fatal "Run as root (or use sudo) so the CloudWatch Agent configuration can be updated."

        [[ -x "$CW_AGENT_CTL" ]] \
            || fatal "CloudWatch Agent control utility not executable: $CW_AGENT_CTL"

        mkdir -p "$CW_AGENT_CONFIG_DIR"
        [[ -d "$CW_AGENT_CONFIG_DIR" ]] \
            || fatal "CloudWatch Agent configuration directory is unavailable: $CW_AGENT_CONFIG_DIR"
    fi
}

classify_file() {
    # Prints: <job-id>|<log-type>
    local name="$1"
    local job log_type

    case "$name" in
        *.def.log)
            job=${name%.def.log}
            log_type="def"
            ;;
        *.dtf.log)
            job=${name%.dtf.log}
            log_type="dtf"
            ;;
        *.log)
            job=${name%.log}
            log_type="main"
            ;;
        *)
            return 1
            ;;
    esac

    [[ -n "$job" ]] || return 1

    if [[ ! "$job" =~ ^[A-Za-z0-9._-]+$ ]]; then
        warn "Skipping unsupported job ID '$job' from file '$name'"
        return 1
    fi

    printf '%s|%s\n' "$job" "$log_type"
}

list_candidate_files() {
    if ((MAX_FILE_AGE_MINUTES > 0)); then
        find "$LOG_DIR" \
            -maxdepth 1 \
            -type f \
            -name '*.log' \
            -mmin "-${MAX_FILE_AGE_MINUTES}" \
            -print \
            | LC_ALL=C sort
    else
        find "$LOG_DIR" \
            -maxdepth 1 \
            -type f \
            -name '*.log' \
            -print \
            | LC_ALL=C sort
    fi
}

generate_config() {
    local output="$1"
    local file name classification job log_type
    local first=true
    local count=0

    local escaped_group
    escaped_group=$(json_escape "$LOG_GROUP")

    {
        printf '{\n'
        printf '  "logs": {\n'
        printf '    "logs_collected": {\n'
        printf '      "files": {\n'
        printf '        "collect_list": [\n'

        while IFS= read -r file; do
            [[ -n "$file" ]] || continue
            name=${file##*/}

            if ! classification=$(classify_file "$name"); then
                continue
            fi

            job=${classification%%|*}
            log_type=${classification#*|}

            if [[ "$first" == false ]]; then
                printf ',\n'
            fi
            first=false

            printf '          {\n'
            printf '            "file_path": "%s",\n' "$(json_escape "$file")"
            printf '            "log_group_name": "%s",\n' "$escaped_group"
            printf '            "log_stream_name": "%s/{instance_id}/%s"\n' \
                "$(json_escape "$job")" \
                "$(json_escape "$log_type")"
            printf '          }'

            count=$((count + 1))
        done < <(list_candidate_files)

        printf '\n'
        printf '        ]\n'
        printf '      }\n'
        printf '    }\n'
        printf '  }\n'
        printf '}\n'
    } > "$output"

    printf '%s\n' "$count"
}

apply_config() {
    local candidate="$1"
    local backup=""
    local had_previous=false

    if [[ -f "$GENERATED_CONFIG_FILE" ]]; then
        had_previous=true
        backup=$(mktemp "${GENERATED_CONFIG_FILE}.backup.XXXXXX")
        cp -p "$GENERATED_CONFIG_FILE" "$backup"
    fi

    # Install candidate at the stable filename before append-config. AWS
    # identifies appended fragments by filename, so keeping this name stable
    # allows later refreshes to replace the previous fragment.
    install -m 0644 "$candidate" "$GENERATED_CONFIG_FILE"

    if "$CW_AGENT_CTL" \
        -a append-config \
        -m ec2 \
        -c "file:${GENERATED_CONFIG_FILE}" \
        -s; then
        [[ -n "$backup" ]] && rm -f "$backup"
        log "CloudWatch Agent configuration updated successfully."
        return 0
    fi

    warn "CloudWatch Agent rejected or failed to apply the generated fragment."

    if [[ "$had_previous" == true && -n "$backup" && -f "$backup" ]]; then
        mv -f "$backup" "$GENERATED_CONFIG_FILE"
        warn "Restored previous generated configuration so the next run can retry."
    else
        rm -f "$GENERATED_CONFIG_FILE"
        [[ -n "$backup" ]] && rm -f "$backup"
    fi

    return 1
}

main() {
    validate_environment
    acquire_lock

    local temp_parent temp_file count

    if [[ "$DRY_RUN" == true ]]; then
        temp_parent=${TMPDIR:-/tmp}
    else
        temp_parent="$CW_AGENT_CONFIG_DIR"
    fi

    temp_file=$(mktemp "${temp_parent%/}/xyz-job-logs.XXXXXX.json")
    trap 'rm -f "${temp_file:-}"; release_lock' EXIT INT TERM HUP

    count=$(generate_config "$temp_file")

    if ((count == 0)); then
        rm -f "$temp_file"
        log "No supported job log files found; leaving the current agent configuration unchanged."
        return 0
    fi

    log "Discovered $count supported job log file(s)."

    if [[ "$DRY_RUN" == true ]]; then
        cat "$temp_file"
        rm -f "$temp_file"
        return 0
    fi

    if [[ "$FORCE" == false && -f "$GENERATED_CONFIG_FILE" ]] \
        && cmp -s "$temp_file" "$GENERATED_CONFIG_FILE"; then
        rm -f "$temp_file"
        log "CloudWatch job log configuration unchanged."
        return 0
    fi

    log "CloudWatch job log configuration changed; applying agent fragment."
    apply_config "$temp_file"
    rm -f "$temp_file"
}

main
