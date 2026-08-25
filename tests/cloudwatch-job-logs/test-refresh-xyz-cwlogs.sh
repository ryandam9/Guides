#!/usr/bin/env bash
# Smoke tests for scripts/cloudwatch-job-logs/refresh-xyz-cwlogs.sh

set -euo pipefail
IFS=$'\n\t'

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SCRIPT="$REPO_ROOT/scripts/cloudwatch-job-logs/refresh-xyz-cwlogs.sh"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

pass() {
    printf 'PASS: %s\n' "$*"
}

assert_contains() {
    local file="$1"
    local text="$2"
    grep -F -- "$text" "$file" >/dev/null 2>&1 \
        || fail "Expected '$text' in $file"
}

assert_not_contains() {
    local file="$1"
    local text="$2"
    if grep -F -- "$text" "$file" >/dev/null 2>&1; then
        fail "Did not expect '$text' in $file"
    fi
}

[[ -f "$SCRIPT" ]] || fail "Script not found: $SCRIPT"

bash -n "$SCRIPT"
pass "bash syntax"

TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT INT TERM HUP

LOG_DIR="$TMP_ROOT/log"
mkdir -p "$LOG_DIR"

: > "$LOG_DIR/j1.log"
: > "$LOG_DIR/j1.def.log"
: > "$LOG_DIR/j1.dtf.log"
: > "$LOG_DIR/job-20260826-001.log"
: > "$LOG_DIR/batch.42.def.log"
: > "$LOG_DIR/bad job.log"

SETTINGS="$TMP_ROOT/settings"
cat > "$SETTINGS" <<EOF
LOG_DIR="$LOG_DIR"
LOG_GROUP="/test/xyz/jobs"
MAX_FILE_AGE_MINUTES=0
LOCK_DIR="$TMP_ROOT/lock"
EOF

OUTPUT="$TMP_ROOT/output.json"
ERRORS="$TMP_ROOT/errors.txt"

XYZ_CWLOGS_SETTINGS_FILE="$SETTINGS" \
    bash "$SCRIPT" --dry-run > "$OUTPUT" 2> "$ERRORS"

assert_contains "$OUTPUT" '"log_group_name": "/test/xyz/jobs"'
assert_contains "$OUTPUT" '"log_stream_name": "j1/{instance_id}/main"'
assert_contains "$OUTPUT" '"log_stream_name": "j1/{instance_id}/def"'
assert_contains "$OUTPUT" '"log_stream_name": "j1/{instance_id}/dtf"'
assert_contains "$OUTPUT" '"log_stream_name": "job-20260826-001/{instance_id}/main"'
assert_contains "$OUTPUT" '"log_stream_name": "batch.42/{instance_id}/def"'
assert_not_contains "$OUTPUT" 'bad job'
assert_contains "$ERRORS" "Skipping unsupported job ID 'bad job'"
pass "job/type mapping and unsafe-name rejection"

if command -v python3 >/dev/null 2>&1; then
    # The script logs discovery information to stdout before the JSON in
    # normal operation, so extract the JSON payload starting at the first '{'.
    JSON_ONLY="$TMP_ROOT/json-only.json"
    awk 'found || /^\{/ {found=1; print}' "$OUTPUT" > "$JSON_ONLY"
    python3 -m json.tool "$JSON_ONLY" >/dev/null
    pass "generated JSON parses"
fi

# Validate age filtering when GNU touch supports relative dates.
if touch -d '2 hours ago' "$LOG_DIR/job-20260826-001.log" 2>/dev/null; then
    cat > "$SETTINGS" <<EOF
LOG_DIR="$LOG_DIR"
LOG_GROUP="/test/xyz/jobs"
MAX_FILE_AGE_MINUTES=60
LOCK_DIR="$TMP_ROOT/lock-age"
EOF

    AGE_OUTPUT="$TMP_ROOT/age-output.json"
    XYZ_CWLOGS_SETTINGS_FILE="$SETTINGS" \
        bash "$SCRIPT" --dry-run > "$AGE_OUTPUT" 2>/dev/null

    assert_not_contains "$AGE_OUTPUT" 'job-20260826-001/{instance_id}/main'
    assert_contains "$AGE_OUTPUT" 'j1/{instance_id}/main'
    pass "MAX_FILE_AGE_MINUTES filtering"
fi

printf 'All CloudWatch job-log discovery smoke tests passed.\n'
