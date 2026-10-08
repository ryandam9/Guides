#!/usr/bin/env bash
#
# yarnapps.sh — list YARN applications with Oozie launcher names decoded.
#
# Runs `yarn application -list` and splits each Oozie launcher name
# (oozie:launcher:T=<type>:W=<workflow>:A=<action>:ID=<job-id>) into
# separate SCRIPT / ACTION / WORKFLOW / WORKFLOW_ID columns, so you can
# see at a glance which Oozie workflow, action, and job ID each YARN
# application belongs to. The WORKFLOW_ID column feeds straight into
# `oozie job -info <id>`.
#
# Usage:
#   ./yarnapps.sh [pattern]      # pattern filters rows (default: dummy-acc)
#   ./yarnapps.sh                # only apps matching dummy-acc
#   ./yarnapps.sh my_workflow    # only apps whose row matches my_workflow
#   ./yarnapps.sh .              # everything
#
# Can also be sourced to get the yarnapps function in your shell:
#   source yarnapps.sh && yarnapps my_workflow
#
# Note: parses the app-name field ($2), so app names must not contain
# spaces — true for Oozie launcher names and script names.

yarnapps() {
  local pattern="${1:-dummy-acc}"
  yarn application -appStates ALL -list 2>/dev/null |
  awk -v pattern="$pattern" '
  $0 ~ pattern {
    app  = $1
    name = $2
    # Strip the launcher prefix for ANY action type (shell, hive2, spark, ...)
    sub(/^oozie:launcher:T=[^:]*:W=/, "", name)

    script   = ""
    action   = ""
    workflow = ""
    wfid     = ""

    # Direct script applications usually end with a known script extension.
    if (name ~ /\.(py|sh|hql|sql)$/) {
      script = name
    } else {
      # Oozie-style names look like:
      # workflow_name:A=action_name:ID=0000123-260730101010101-oozie-oozi-W
      workflow = name
      sub(/:A=.*/, "", workflow)

      action = name
      sub(/^.*:A=/, "", action)
      sub(/:.*/, "", action)

      if (name ~ /:ID=/) {
        wfid = name
        sub(/^.*:ID=/, "", wfid)
      }
    }

    print app "|" script "|" action "|" workflow "|" wfid
  }
  ' |
  sort -t'|' -k1,1 |
  awk 'BEGIN { print "APPLICATION|SCRIPT|ACTION|WORKFLOW|WORKFLOW_ID" } { print }' |
  column -s'|' -t
}

# Run directly (not sourced) → execute with the given args.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  yarnapps "$@"
fi
