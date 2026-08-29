#!/usr/bin/env bash
# Build four independent XML databases, one worker per scenario group.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
EXE_ROOT="$REPO_ROOT/exe"
CONFIG_ROOT="$HERE/configurations/database-archive"
OUTPUT_ROOT="$REPO_ROOT/output/ai-data-center-databases"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_ROOT="$REPO_ROOT/output/ai-data-center-run-logs/$RUN_ID"
BACKUP_ROOT="$REPO_ROOT/output/ai-data-center-database-backups/$RUN_ID"
REPLACE=0

usage() {
    echo "Usage: bash exe/ai-data-center/run-database-archive.sh [--replace]"
    echo
    echo "Without --replace, the runner refuses to overwrite an existing database."
    echo "With --replace, existing databases are moved to a timestamped backup."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --replace)
            REPLACE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

GROUPS=(
    efficiency-low
    efficiency-medium
    efficiency-high
    demand-constant
)

python3 "$HERE/verify-runtime.py"

if [[ -z "${LD_PRELOAD:-}" && -f /usr/local/lib64/libtbb.so.12 ]]; then
    export LD_PRELOAD=/usr/local/lib64/libtbb.so.12
fi

mkdir -p "$OUTPUT_ROOT" "$LOG_ROOT"

for group in "${GROUPS[@]}"; do
    database="$OUTPUT_ROOT/$group"
    if [[ -e "$database" ]]; then
        if [[ $REPLACE -eq 0 ]]; then
            echo "Refusing to overwrite existing database: $database" >&2
            echo "Rerun with --replace to move it into a timestamped backup." >&2
            exit 1
        fi
        mkdir -p "$BACKUP_ROOT"
        mv "$database" "$BACKUP_ROOT/$group"
    fi
done

run_group() {
    local group="$1"
    local config_dir="$CONFIG_ROOT/$group"
    local group_log="$LOG_ROOT/group-$group.summary"
    local configs=()
    mapfile -t configs < <(find "$config_dir" -maxdepth 1 -type f -name '*.xml' -print | sort)
    if [[ ${#configs[@]} -ne 6 ]]; then
        echo "[$group] expected 6 configurations, found ${#configs[@]}" > "$group_log"
        return 1
    fi

    for config in "${configs[@]}"; do
        local filename
        local scenario
        local log
        filename="$(basename "$config")"
        scenario="${filename%.xml}"
        log="$LOG_ROOT/${group}__${scenario}.log"
        (
            cd "$EXE_ROOT"
            ./gcam.exe -C "ai-data-center/configurations/database-archive/$group/$filename"
        ) > "$log" 2>&1

        if grep -q "did not solve" "$log" || ! grep -q "Period 11: 2050" "$log"; then
            echo "[$group] $scenario: FAILED, group stopped, log $log" >> "$group_log"
            return 1
        fi
        echo "[$group] $scenario: ok" >> "$group_log"
    done
    echo "[$group] GROUP COMPLETE, 6 of 6" >> "$group_log"
}

pids=()
for group in "${GROUPS[@]}"; do
    run_group "$group" &
    pids+=("$!")
done

failed=0
for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
done

echo "Run logs: $LOG_ROOT"
for group in "${GROUPS[@]}"; do
    summary="$LOG_ROOT/group-$group.summary"
    if [[ -f "$summary" ]]; then
        cat "$summary"
    else
        echo "[$group] FAILED before a summary was written"
        failed=1
    fi
done

if [[ $failed -eq 0 ]]; then
    echo "ALL 4 DATABASES BUILT, 24 scenarios"
else
    echo "AT LEAST ONE GROUP FAILED, inspect the saved logs" >&2
fi
exit "$failed"
