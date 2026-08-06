# Grepping GitHub Actions Run Logs

## The problem

The Actions web UI has a search box per job, but it can't search across
runs, can't use regex, and is painful for long logs. The fix: pull logs
down with the `gh` CLI and use `grep` like you would on any file.

Everything below needs the [GitHub CLI](https://cli.github.com/)
(`brew install gh`) and a one-time login:

```sh
gh auth login

# For GitHub Enterprise at work, point gh at your instance:
export GH_HOST=github.mycompany.com
gh auth login --hostname github.mycompany.com
```

Run the commands from inside a clone of the repo, or add
`-R owner/repo` to target any repo explicitly.

## Find the run you care about

```sh
gh run list                                  # recent runs, all workflows
gh run list --workflow build.yml             # one workflow
gh run list --status failure                 # only failures
gh run list --branch main --limit 30         # by branch
gh run list --user someone                   # by who triggered it
```

Each line shows a run ID — that's what the log commands take. For
scripting, get IDs cleanly with JSON output:

```sh
gh run list --status failure --limit 10 --json databaseId,displayTitle \
  --jq '.[].databaseId'
```

## Grep a single run

```sh
gh run view 30998126749 --log         | grep -i 'error'
gh run view 30998126749 --log-failed  | grep -iE 'error|failed|exception'
```

- `--log` streams the complete log of every job in the run.
- `--log-failed` limits it to the steps that failed — usually what you
  want, and much less noise.

Each log line is prefixed with `job name<TAB>step name<TAB>timestamp`, so
grep results tell you *where* the match happened for free. Filter to one
job's lines with an initial grep on the job name:

```sh
gh run view 30998126749 --log | grep '^lint-and-smoke-test' | grep -i warning
```

Context flags work as usual — `grep -B2 -A5 'Traceback'` shows the lines
around a Python stack trace.

## Grep across many runs

Loop over run IDs and label the output, e.g. "which of the last 50 runs
hit this flaky DNS error":

```sh
for id in $(gh run list --limit 50 --json databaseId --jq '.[].databaseId'); do
  gh run view "$id" --log 2>/dev/null \
    | grep -q 'Temporary failure in name resolution' \
    && echo "match in run $id"
done
```

Fetching 50 logs takes a while; narrow with `--workflow` / `--branch` /
`--status failure` first when you can.

## Download logs as files

For repeated grepping (or `less`, `awk`, an editor), download once
instead of re-fetching:

```sh
# whole run as a zip: one .txt per step
gh api "repos/{owner}/{repo}/actions/runs/RUN_ID/logs" > run-logs.zip
unzip -o run-logs.zip -d run-logs
grep -rn 'OutOfMemoryError' run-logs/

# or a single job as plain text (job IDs: gh run view RUN_ID --json jobs)
gh api "repos/{owner}/{repo}/actions/jobs/JOB_ID/logs" > job.log
```

`{owner}/{repo}` is literal — `gh` fills it in from the current
directory's clone.

Archiving a month of failure logs before they expire:

```sh
mkdir -p logs
for id in $(gh run list --status failure --limit 100 --json databaseId --jq '.[].databaseId'); do
  gh api "repos/{owner}/{repo}/actions/runs/$id/logs" > "logs/$id.zip" 2>/dev/null || true
done
```

## Watching a live run

`--log` only works on completed runs. For an in-progress run:

```sh
gh run watch RUN_ID          # live status until it finishes
gh run watch RUN_ID && gh run view RUN_ID --log-failed | grep -i error
```

## Gotchas

- **Logs expire.** Default retention is 90 days (org/repo configurable,
  and often shorter on Enterprise). Expired runs 404 on the log
  endpoints — download anything you'll need for postmortems.
- **`--log` on a running run** errors out ("run is still in progress");
  wait or use `gh run watch`.
- **Permissions.** Reading logs needs the repo's Actions read permission;
  on Enterprise your token/SSO session must be authorized for the org.
- **Huge logs.** A single run's logs can be hundreds of MB. Prefer
  `--log-failed`, or download the zip once rather than streaming
  repeatedly.
- **In-workflow alternative.** If you control the workflow, a step like
  `grep -c 'pattern' output.log >> "$GITHUB_STEP_SUMMARY"` surfaces
  counts right on the run page — no local grepping needed for routine
  checks.
