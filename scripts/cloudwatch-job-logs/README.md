# XYZ CloudWatch Job Log Collector

This directory contains the deployable implementation described in [`docs/cloudwatch-job-log-architecture.md`](../../docs/cloudwatch-job-log-architecture.md).

## What it does

On each EC2 instance, it discovers files such as:

```text
/app/xyz/log/j1.log
/app/xyz/log/j1.def.log
/app/xyz/log/j1.dtf.log
```

and maintains explicit Amazon CloudWatch Agent entries that publish to:

```text
Log group: /app/xyz/jobs

j1/{instance_id}/main
j1/{instance_id}/def
j1/{instance_id}/dtf
```

The same files can be deployed to all four EC2 instances because CloudWatch Agent expands `{instance_id}` itself.

## Files

| File | Purpose |
|---|---|
| `refresh-xyz-cwlogs.sh` | Discovers job logs, generates the CloudWatch Agent fragment, compares it with the current fragment, and applies changes only when needed |
| `xyz-cwlogs-refresh.env` | Default host settings installed to `/etc/default/xyz-cwlogs-refresh` |
| `xyz-cwlogs-refresh.service` | One-shot systemd service |
| `xyz-cwlogs-refresh.timer` | Runs discovery about once per minute, with a small randomized delay |
| `install.sh` | Installs/enables the implementation on one host |

## Prerequisites

- Linux with systemd.
- Amazon CloudWatch Agent already installed.
- Application logs under `/app/xyz/log` or another configured directory.
- EC2 instance role with appropriate CloudWatch Logs permissions.
- Root/sudo access for installation.

No AWS CLI is required by the discovery implementation.

## Install

From this directory:

```bash
sudo bash install.sh
```

The installer intentionally does **not** overwrite an existing:

```text
/etc/default/xyz-cwlogs-refresh
```

so host-specific settings survive upgrades.

## Settings

Edit:

```bash
sudo vi /etc/default/xyz-cwlogs-refresh
```

Default:

```bash
LOG_DIR="/app/xyz/log"
LOG_GROUP="/app/xyz/jobs"
MAX_FILE_AGE_MINUTES=0
```

Then trigger a refresh:

```bash
sudo systemctl start xyz-cwlogs-refresh.service
```

## Dry run

Preview the generated fragment without modifying CloudWatch Agent:

```bash
sudo /usr/local/sbin/refresh-xyz-cwlogs.sh --dry-run
```

## Force apply

Normally the script does nothing when the generated JSON is unchanged.

To force re-application:

```bash
sudo /usr/local/sbin/refresh-xyz-cwlogs.sh --force
```

## Status and logs

```bash
systemctl status xyz-cwlogs-refresh.timer
```

```bash
systemctl list-timers --all | grep xyz-cwlogs
```

```bash
journalctl -u xyz-cwlogs-refresh.service -n 100 --no-pager
```

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status
```

```bash
tail -100 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

## Generated configuration

The active generated fragment is:

```text
/opt/aws/amazon-cloudwatch-agent/etc/xyz-job-logs.json
```

Do not hand-edit this file; edit `/etc/default/xyz-cwlogs-refresh` or the source script instead.

## Supported file names

```text
<job-id>.log
<job-id>.def.log
<job-id>.dtf.log
```

Supported job-ID characters:

```text
A-Z a-z 0-9 . _ -
```

## Tests

From the repository root:

```bash
bash tests/cloudwatch-job-logs/test-refresh-xyz-cwlogs.sh
```

The smoke test validates:

- shell syntax;
- `main`, `def`, and `dtf` mapping;
- `{instance_id}` stream naming;
- job IDs containing `-` and `.`;
- unsafe filename rejection;
- generated JSON syntax when `python3` is available;
- file-age filtering when GNU `touch` supports relative dates.

## Removal / rollback

Disable the timer:

```bash
sudo systemctl disable --now xyz-cwlogs-refresh.timer
```

Because this project appends a fragment to the CloudWatch Agent's effective configuration, use your normal CloudWatch Agent deployment process to re-apply the known-good base configuration if you want to remove the fragment from the running agent completely.
