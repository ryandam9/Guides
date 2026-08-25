# CloudWatch Job Log Architecture for Multi-Instance EC2 Applications

> **Scope:** Collect job-specific log files from four Linux EC2 instances and preserve an easy-to-navigate job → instance → log-type structure in Amazon CloudWatch Logs.
>
> **Version snapshot:** 26 August 2026. CloudWatch Agent behaviour and limits can change; re-check the linked AWS documentation during major upgrades.

---

## 1. Problem statement

The application runs on **four Linux EC2 instances**. Each instance writes application logs under:

```text
/app/xyz/log
```

Each process/job has a job ID and produces three files:

```text
j1.log
j1.def.log
j1.dtf.log
```

A second job might produce:

```text
j2.log
j2.def.log
j2.dtf.log
```

The operational requirement is:

> Given a job ID, quickly find all logs for that job in CloudWatch Logs, while still knowing which EC2 instance and which physical log type produced each event.

### Goals

1. Keep one predictable CloudWatch Logs location for the application.
2. Make **job ID the primary navigation/search key**.
3. Keep logs from the four EC2 instances separate.
4. Keep `main`, `def`, and `dtf` logs separate.
5. Automatically discover new job IDs/files without manually editing CloudWatch Agent configuration.
6. Avoid restarting/reconfiguring the CloudWatch Agent when nothing changed.
7. Reuse the same implementation on all four instances.
8. Avoid an AWS CLI dependency on the EC2 hosts.
9. Preserve the instance's existing CloudWatch Agent configuration by using an appended configuration fragment.
10. Make the automation idempotent and safe to run repeatedly.

### Non-goals

- Changing the application's current file naming convention.
- Parsing application log contents into JSON.
- Replacing CloudWatch Agent with Fluent Bit, OpenTelemetry Collector, or a custom log shipper.
- Creating one CloudWatch log group per job.

---

## 2. Recommended CloudWatch design

Use **one shared log group**:

```text
/app/xyz/jobs
```

Use a logical stream naming convention of:

```text
<job-id>/{instance_id}/<log-type>
```

For example:

```text
j1/i-0123456789abcdef0/main
j1/i-0123456789abcdef0/def
j1/i-0123456789abcdef0/dtf

j1/i-0fedcba9876543210/main
j1/i-0fedcba9876543210/def
j1/i-0fedcba9876543210/dtf

j2/i-0123456789abcdef0/main
j2/i-0123456789abcdef0/def
j2/i-0123456789abcdef0/dtf
```

> CloudWatch Logs log streams are not real nested folders. The `/` characters are part of the stream name. They are used here as a **logical hierarchy and naming convention**.

### Mapping

| Linux file | CloudWatch log group | CloudWatch stream |
|---|---|---|
| `/app/xyz/log/j1.log` | `/app/xyz/jobs` | `j1/{instance_id}/main` |
| `/app/xyz/log/j1.def.log` | `/app/xyz/jobs` | `j1/{instance_id}/def` |
| `/app/xyz/log/j1.dtf.log` | `/app/xyz/jobs` | `j1/{instance_id}/dtf` |
| `/app/xyz/log/j2.log` | `/app/xyz/jobs` | `j2/{instance_id}/main` |
| `/app/xyz/log/j2.def.log` | `/app/xyz/jobs` | `j2/{instance_id}/def` |
| `/app/xyz/log/j2.dtf.log` | `/app/xyz/jobs` | `j2/{instance_id}/dtf` |

AWS CloudWatch Agent expands `{instance_id}` automatically on EC2. Supported variables for log stream names include `{instance_id}`, `{hostname}`, `{local_hostname}`, and `{ip_address}`.

### Why job ID comes first

The most common support question is expected to be:

> What happened to job `j1`?

Therefore this is preferred:

```text
j1/{instance_id}/main
```

over:

```text
{instance_id}/j1/main
```

With job-first naming, every stream for `j1` shares the same prefix.

---

## 3. Architecture

```mermaid
flowchart LR
    subgraph E[EC2 fleet - 4 Linux instances]
        E1[EC2-1\n/app/xyz/log]
        E2[EC2-2\n/app/xyz/log]
        E3[EC2-3\n/app/xyz/log]
        E4[EC2-4\n/app/xyz/log]
    end

    subgraph D[Per-instance discovery]
        T[systemd timer\nevery ~60 sec]
        S[refresh-xyz-cwlogs.sh]
        C[generated CloudWatch Agent\nconfig fragment]
        A[Amazon CloudWatch Agent]
        T --> S --> C --> A
    end

    subgraph CW[Amazon CloudWatch Logs]
        G[Log group\n/app/xyz/jobs]
        J1[j1/{instance_id}/main\nj1/{instance_id}/def\nj1/{instance_id}/dtf]
        J2[j2/{instance_id}/main\nj2/{instance_id}/def\nj2/{instance_id}/dtf]
        G --> J1
        G --> J2
    end

    E1 --> D
    E2 --> D
    E3 --> D
    E4 --> D
    A --> G
```

Each instance runs the same script and systemd units. There is no central coordinator.

---

## 4. Why a discovery script is required

CloudWatch Agent supports glob patterns in `file_path`, but there are two important constraints for this use case.

### 4.1 The stream name cannot capture the job ID from the filename

CloudWatch Agent can substitute built-in values such as `{instance_id}`, but it does **not** provide a `{filename}` variable or regex capture that would transform:

```text
/app/xyz/log/j1.def.log
```

into:

```text
j1/{instance_id}/def
```

Therefore the job ID must be discovered outside the agent configuration.

### 4.2 One `*.log` wildcard is not appropriate for all job files

AWS documents that when a wildcard matches a series of files, the agent pushes the latest matching file based on modification time and recommends wildcards for a series of files of the **same type**, not multiple different kinds of files.

For this workload, this is therefore intentionally avoided:

```json
{
  "file_path": "/app/xyz/log/*.log",
  "log_group_name": "/app/xyz/jobs"
}
```

Instead, the discovery script generates one explicit `collect_list` entry for each physical job log file.

---

## 5. Dynamic discovery flow

On each EC2 instance:

```text
systemd timer
     |
     v
scan /app/xyz/log
     |
     +--> j1.log      -> j1/{instance_id}/main
     +--> j1.def.log  -> j1/{instance_id}/def
     +--> j1.dtf.log  -> j1/{instance_id}/dtf
     |
     v
generate xyz-job-logs.json.tmp
     |
     v
compare with current xyz-job-logs.json
     |
     +--> identical --------> exit; no agent action
     |
     +--> changed ----------> atomically replace fragment
                                  |
                                  v
                         CloudWatch Agent append-config
```

### Important property: no unnecessary reloads

The timer may run every minute, but the CloudWatch Agent is only reconfigured when the generated file list changes.

Normal run:

```text
12:00 scan -> no change -> exit
12:01 scan -> no change -> exit
12:02 scan -> no change -> exit
```

New job appears:

```text
12:03 j27.log appears
12:03 generated configuration changes
12:03 append-config is applied
12:03 j27/{instance_id}/main begins shipping
```

The service uses `RandomizedDelaySec` so the four hosts do not all refresh at exactly the same second.

---

## 6. Repository implementation

The implementation is stored under:

```text
scripts/cloudwatch-job-logs/
```

Files:

```text
scripts/cloudwatch-job-logs/
├── README.md
├── install.sh
├── refresh-xyz-cwlogs.sh
├── xyz-cwlogs-refresh.env
├── xyz-cwlogs-refresh.service
└── xyz-cwlogs-refresh.timer

tests/cloudwatch-job-logs/
└── test-refresh-xyz-cwlogs.sh
```

### Runtime installation paths

| Repository file | Installed path |
|---|---|
| `refresh-xyz-cwlogs.sh` | `/usr/local/sbin/refresh-xyz-cwlogs.sh` |
| `xyz-cwlogs-refresh.env` | `/etc/default/xyz-cwlogs-refresh` |
| `xyz-cwlogs-refresh.service` | `/etc/systemd/system/xyz-cwlogs-refresh.service` |
| `xyz-cwlogs-refresh.timer` | `/etc/systemd/system/xyz-cwlogs-refresh.timer` |
| generated fragment | `/opt/aws/amazon-cloudwatch-agent/etc/xyz-job-logs.json` |

---

## 7. Generated CloudWatch Agent configuration

For these files:

```text
/app/xyz/log/j1.log
/app/xyz/log/j1.def.log
/app/xyz/log/j1.dtf.log
```

one instance generates a fragment equivalent to:

```json
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/app/xyz/log/j1.log",
            "log_group_name": "/app/xyz/jobs",
            "log_stream_name": "j1/{instance_id}/main"
          },
          {
            "file_path": "/app/xyz/log/j1.def.log",
            "log_group_name": "/app/xyz/jobs",
            "log_stream_name": "j1/{instance_id}/def"
          },
          {
            "file_path": "/app/xyz/log/j1.dtf.log",
            "log_group_name": "/app/xyz/jobs",
            "log_stream_name": "j1/{instance_id}/dtf"
          }
        ]
      }
    }
  }
}
```

The literal `{instance_id}` remains in the generated JSON. CloudWatch Agent expands it at runtime.

---

## 8. Configuration options

The script reads:

```text
/etc/default/xyz-cwlogs-refresh
```

Default values:

```bash
LOG_DIR="/app/xyz/log"
LOG_GROUP="/app/xyz/jobs"
MAX_FILE_AGE_MINUTES=0
```

### `LOG_DIR`

Directory containing job log files.

### `LOG_GROUP`

Shared CloudWatch Logs log group for this application.

### `MAX_FILE_AGE_MINUTES`

Controls how many existing files are retained in the generated active collection configuration.

```text
0     = include all matching files
1440  = files modified in approximately the last 24 hours
2880  = files modified in approximately the last 48 hours
```

For correctness, the repository default is `0`.

If the local log directory retains thousands of historical files, set a bounded age such as `2880` after confirming that jobs normally finish inside that window. Once a completed file has already been fully shipped, it does not need to remain forever in the active agent fragment.

> Do not use a short age window if a job can remain quiet for longer than that window and later continue writing to the same file.

---

## 9. Job ID rules

The script accepts job IDs containing:

```text
A-Z a-z 0-9 . _ -
```

Examples:

```text
j1
job-20260826-001
ABC_123
batch.42
```

A filename such as:

```text
job 1.log
```

is deliberately skipped because the embedded space falls outside the safe job-ID rule.

The recognised suffixes are:

| Suffix | Stream log type |
|---|---|
| `.log` | `main` |
| `.def.log` | `def` |
| `.dtf.log` | `dtf` |

Suffix matching checks `def` and `dtf` before the general `.log` case.

---

## 10. Same job ID on multiple instances

This is safe because `{instance_id}` makes the streams distinct.

For example, job `j1` on four hosts can create:

```text
j1/i-aaa111/main
j1/i-aaa111/def
j1/i-aaa111/dtf

j1/i-bbb222/main
j1/i-bbb222/def
j1/i-bbb222/dtf

j1/i-ccc333/main
j1/i-ccc333/def
j1/i-ccc333/dtf

j1/i-ddd444/main
j1/i-ddd444/def
j1/i-ddd444/dtf
```

### If job IDs are reused on different days

The default design assumes a job ID identifies a run well enough for operational searching. If the application reuses a small fixed set of IDs such as `j1`, `j2`, `j3` every day, the same CloudWatch streams will contain events from multiple dates.

That is still searchable by timestamp, but if strict run-level separation is required, the **best solution is to put a unique run ID or run date into the application's filename/job ID**. For example:

```text
20260826-j1.log
20260826-j1.def.log
20260826-j1.dtf.log
```

which naturally produces:

```text
20260826-j1/{instance_id}/main
20260826-j1/{instance_id}/def
20260826-j1/{instance_id}/dtf
```

Avoid inferring a run date from a file's changing modification time; a long-running process can cross midnight and make that mapping unstable.

---

## 11. CloudWatch Agent configuration strategy

The implementation uses:

```text
amazon-cloudwatch-agent-ctl -a append-config
```

rather than replacing the host's primary CloudWatch Agent configuration.

AWS supports composing multiple configuration files this way. When `append-config` is invoked again with a configuration file having the **same filename**, AWS documents that the new fragment overwrites the information from the previous fragment with that filename instead of accumulating another duplicate fragment.

This is exactly what the discovery service needs:

```text
existing infrastructure/metrics config
               +
xyz-job-logs.json generated fragment
               =
running CloudWatch Agent configuration
```

### Failure-safe update

The script:

1. generates a temporary file;
2. compares it to the currently installed fragment;
3. backs up the previous fragment;
4. atomically installs the new fragment;
5. calls `append-config`;
6. restores the previous fragment if the agent command fails.

This matters because otherwise a failed agent reload followed by an unchanged local JSON file could cause future timer runs to incorrectly believe there is nothing left to retry.

---

## 12. Concurrency and idempotency

### Locking

A lock directory under `/run` prevents overlapping executions.

This protects against cases such as:

```text
timer run starts
    |
    +-- slow CloudWatch Agent reload
            |
            +-- next timer fires
```

The second invocation exits without modifying configuration.

### Deterministic output

Discovered file paths are sorted before JSON generation. Therefore the same directory state produces byte-for-byte identical JSON.

That makes a simple `cmp` reliable and avoids unnecessary agent updates.

---

## 13. Deployment

### Prerequisites on each of the four EC2 instances

1. Amazon CloudWatch Agent is installed.
2. The instance role can publish to the target log group.
3. The agent can read `/app/xyz/log` and its files.
4. `systemd` is present.
5. The deployment is run as root or with equivalent sudo permissions.

### Install from a cloned Guides repository

From the repository root:

```bash
cd scripts/cloudwatch-job-logs
sudo ./install.sh
```

The installer:

- validates the CloudWatch Agent control utility exists;
- installs the refresh script;
- installs the environment file if one does not already exist;
- installs the systemd service and timer;
- reloads systemd;
- enables the timer;
- runs one immediate discovery pass.

The installer **does not overwrite an existing** `/etc/default/xyz-cwlogs-refresh`; this protects local customisation.

### Verify timer

```bash
systemctl status xyz-cwlogs-refresh.timer
```

```bash
systemctl list-timers --all | grep xyz-cwlogs
```

### Run discovery manually

```bash
sudo systemctl start xyz-cwlogs-refresh.service
```

or:

```bash
sudo /usr/local/sbin/refresh-xyz-cwlogs.sh
```

### Preview without changing CloudWatch Agent

```bash
sudo /usr/local/sbin/refresh-xyz-cwlogs.sh --dry-run
```

### Force an agent apply even if content is unchanged

```bash
sudo /usr/local/sbin/refresh-xyz-cwlogs.sh --force
```

---

## 14. Validation checklist

### Local files

```bash
find /app/xyz/log -maxdepth 1 -type f -name '*.log' -printf '%f\n' | sort
```

Expected example:

```text
j1.def.log
j1.dtf.log
j1.log
j2.def.log
j2.dtf.log
j2.log
```

### Generated configuration

```bash
cat /opt/aws/amazon-cloudwatch-agent/etc/xyz-job-logs.json
```

Confirm every local file has one entry and the streams use:

```text
<job>/{instance_id}/<type>
```

### CloudWatch Agent status

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status
```

### CloudWatch Agent log

```bash
tail -100 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

### Discovery service journal

```bash
journalctl -u xyz-cwlogs-refresh.service -n 100 --no-pager
```

Useful expected messages include:

```text
CloudWatch job log configuration unchanged.
```

or:

```text
CloudWatch job log configuration changed; applying agent fragment.
CloudWatch Agent configuration updated successfully.
```

---

## 15. CloudWatch Logs Insights queries

Select the `/app/xyz/jobs` log group.

### Everything for one job across all four instances

```text
fields @timestamp, @logStream, @message
| filter @logStream like /^j1\//
| sort @timestamp asc
```

### One job on one instance

```text
fields @timestamp, @logStream, @message
| filter @logStream like /^j1\/i-0123456789abcdef0\//
| sort @timestamp asc
```

### Only `dtf` logs for a job

```text
fields @timestamp, @logStream, @message
| filter @logStream like /^j1\//
| filter @logStream like /\/dtf$/
| sort @timestamp asc
```

### Search errors for a job

```text
fields @timestamp, @logStream, @message
| filter @logStream like /^j1\//
| filter @message like /(?i)error|exception|failed|fatal/
| sort @timestamp asc
```

### Count messages per instance/log type for a job

```text
fields @logStream
| filter @logStream like /^j1\//
| stats count(*) as events by @logStream
| sort events desc
```

---

## 16. IAM

If the EC2 instances already publish logs through CloudWatch Agent, the required permissions may already be present.

AWS's managed `CloudWatchAgentServerPolicy` is a simple supported option. For environments that require least privilege, the instance role should at minimum have the CloudWatch Logs actions needed to create streams and publish events, and possibly create/configure the target group depending on who manages it.

A common split is:

### Infrastructure-managed log group

Create `/app/xyz/jobs` separately through Terraform/CloudFormation/console and configure retention there. The instance role then only needs permissions to create streams and publish events to that group.

This is preferred in tightly controlled production environments.

### Agent-managed log group

Allow the agent to create the log group if it does not exist. This is simpler but gives the instance broader CloudWatch Logs permissions.

> Prefer infrastructure-as-code for retention, encryption, log-group class, resource policy, subscription filters, alarms, and lifecycle controls.

---

## 17. Retention and cost

Keep retention at the **log-group level** and choose it based on operational and compliance needs.

Example choices:

```text
14 days   short troubleshooting window
30 days   common operational window
90 days   extended operations/audit window
365 days  longer regulated/audit use case
```

The correct value is an organisational decision; the scripts deliberately do not force a retention value.

Cost is driven primarily by ingestion, storage, queries, and any downstream subscriptions/exports—not by the logical `/` characters in stream names.

---

## 18. Failure modes and expected behaviour

| Failure | Behaviour | Operator action |
|---|---|---|
| `/app/xyz/log` missing | Refresh exits with an error | Check mount/application startup/order |
| CloudWatch Agent missing | Refresh exits before changing config | Install/fix agent |
| No matching log files yet | Refresh exits successfully without changing agent | Usually no action |
| Unsupported job ID characters | File is skipped and warning logged | Fix naming rule or intentionally extend script validation |
| Generated config unchanged | No agent command is run | No action |
| Agent `append-config` fails | Previous fragment is restored; service fails so next run retries | Check agent log/config/IAM |
| Two refreshes overlap | Second run exits because lock is held | No action |
| Network outage to CloudWatch | CloudWatch Agent handles its own buffering/retry behaviour | Monitor agent health/disk/network |
| Old local files accumulate | Generated fragment grows | Configure a safe `MAX_FILE_AGE_MINUTES` or local log lifecycle |
| Same job ID reused daily | Events share the same stream across dates | Search by time, or make run/job IDs unique |

---

## 19. Rollout plan for four instances

Recommended rollout:

### Phase 1 — one instance

1. Install files on EC2-1.
2. Run `--dry-run`.
3. Apply the service once.
4. Verify three streams for one known job.
5. Compare local file tail with CloudWatch events.
6. Verify no duplicate/missing lines during a new job creation.

### Phase 2 — second instance

Deploy to EC2-2 and verify the same job creates a second instance-specific stream set.

### Phase 3 — remaining fleet

Deploy to EC2-3 and EC2-4.

### Phase 4 — operational acceptance

Test these support tasks:

- find all `j1` streams;
- combine all `j1` events in Logs Insights;
- isolate one instance;
- isolate `dtf` only;
- search for `ERROR` across all `j1` logs;
- confirm a newly created job appears without manual action.

---

## 20. Rollback

Stop and disable the discovery timer:

```bash
sudo systemctl disable --now xyz-cwlogs-refresh.timer
```

The existing primary CloudWatch Agent configuration is not replaced by this project.

If the dynamic fragment must be removed from the running agent configuration, re-apply the organisation's known-good primary CloudWatch Agent configuration using its normal deployment process. Merely deleting the fragment file is not a substitute for reloading the intended agent configuration.

Before rollback, preserve:

```text
/opt/aws/amazon-cloudwatch-agent/etc/xyz-job-logs.json
```

for troubleshooting if needed.

---

## 21. Alternatives considered

### A. One log group per job

Example:

```text
/app/xyz/jobs/j1
/app/xyz/jobs/j2
```

**Rejected as the default.** It creates many log groups and makes retention, IAM, subscriptions, alarms, and lifecycle management harder.

### B. One stream per instance containing every job

Example:

```text
i-aaa111
i-bbb222
```

**Rejected.** It loses the job-first navigation requirement and mixes all jobs together.

### C. One stream per job, mixing all three file types

Example:

```text
j1/i-aaa111
```

**Rejected.** It becomes harder to distinguish `main`, `def`, and `dtf` provenance and multiple source files writing to one destination can complicate troubleshooting.

### D. Single wildcard config

Example:

```text
/app/xyz/log/*.log
```

**Rejected.** It cannot dynamically derive the job ID for the stream name and AWS recommends wildcard patterns for a series of files of the same kind, not unrelated log types.

### E. Change the application to log structured JSON directly

Potentially valuable later, especially if every line includes fields such as:

```json
{
  "job_id": "j1",
  "component": "dtf",
  "level": "ERROR",
  "message": "..."
}
```

This would improve Logs Insights considerably, but it is a larger application change and is not required to solve the current file collection problem.

---

## 22. Design decision summary

The recommended production design is:

```text
One log group:
/app/xyz/jobs

One stream per job + EC2 instance + log type:
<job-id>/{instance_id}/main
<job-id>/{instance_id}/def
<job-id>/{instance_id}/dtf

One discovery service on every EC2 instance:
refresh-xyz-cwlogs.sh

One lightweight systemd timer:
~60 seconds with small randomized delay
```

This design optimises for the operational question that matters most: **find everything for a job quickly**, without losing host or file-type provenance.

---

## 23. AWS references

- [Manually create or edit the CloudWatch agent configuration file](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Configuration-File-Details.html)
- [Create the CloudWatch agent configuration file](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file.html)
- [CloudWatch agent configuration examples](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/create-cloudwatch-agent-configuration-file-examples.html)
- [CloudWatchAgentServerPolicy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/CloudWatchAgentServerPolicy.html)
