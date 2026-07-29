# Debugging, Verifying & Validating Apache Oozie Workflows on Amazon EMR

A practical reference for working with Oozie workflows, coordinators, and bundles
on an EMR cluster — validation, dry runs, debugging, log collection, and recovery
commands.

> **Where things live on EMR**
>
> | Item | Location |
> |---|---|
> | Oozie server | Runs on the **primary (master) node** |
> | Oozie URL | `http://<master-node>:11000/oozie` |
> | Oozie CLI | `/usr/bin/oozie` (available on the master node) |
> | Server logs | `/var/log/oozie/` (`oozie.log`, `oozie-error.log`, `oozie-audit.log`) |
> | Config | `/etc/oozie/conf/` (`oozie-site.xml`, `oozie-env.sh`) |
> | Shared libs | HDFS: `/user/oozie/share/lib/` |
> | Service control | `sudo systemctl {status,restart} oozie` |

SSH to the master node first:

```sh
ssh -i my-key.pem hadoop@<master-public-dns>
```

Set the Oozie URL once so you can drop `-oozie` from every command:

```sh
export OOZIE_URL=http://localhost:11000/oozie
```

---

## 1. Verify the Oozie server itself

Before debugging a workflow, confirm the server is healthy.

```sh
# Is the server up? (should print: System mode: NORMAL)
oozie admin -status

# Server build version
oozie admin -version

# Effective server configuration
oozie admin -configuration

# Java system properties / OS environment of the server
oozie admin -javasysprops
oozie admin -osenv

# List available sharelibs (spark, hive, pig, sqoop, distcp, ...)
oozie admin -shareliblist
oozie admin -shareliblist spark      # jars inside one sharelib

# Rebuild the sharelib metadata after uploading new jars (no restart needed)
oozie admin -sharelibupdate

# Check queue/instrumentation metrics
oozie admin -instrumentation
oozie admin -metrics
```

Service-level checks on the master node:

```sh
sudo systemctl status oozie
sudo tail -f /var/log/oozie/oozie.log
sudo tail -f /var/log/oozie/oozie-error.log
```

---

## 2. Validate a workflow XML (schema check)

`validate` checks the workflow/coordinator/bundle definition against the XSD
schema **without running anything**. Always do this before submitting.

```sh
# Validate a local file
oozie validate workflow.xml

# Validate a file already uploaded to HDFS (Oozie 4.2+)
oozie validate hdfs:///user/hadoop/apps/my-app/workflow.xml
```

Typical output on success:

```
Valid workflow-app
```

Common validation errors:

| Error | Meaning |
|---|---|
| `E0701` | XML schema error — malformed XML, wrong element order, wrong namespace version |
| `E0505` / `E0504` | App directory or `workflow.xml` does not exist in HDFS |
| `E0710` | Could not read the workflow definition |
| `E0736` | Workflow definition length exceeds limit |

Also lint the raw XML locally before involving Oozie at all:

```sh
xmllint --noout workflow.xml && echo "well-formed"
```

---

## 3. Dry run (submit without executing)

`-dryrun` sends the job through full server-side validation — properties are
resolved, EL expressions evaluated, the definition parsed — but **no actions are
executed** and no job ID is created.

```sh
# Workflow dry run
oozie job -dryrun -config job.properties

# Coordinator dry run — also prints the computed materialization
# (the actions the coordinator *would* create and when)
oozie job -dryrun -config coordinator.properties
```

Success output:

- Workflow: `OK`
- Coordinator: `***coordJob after parsing: ***` followed by the resolved coordinator XML and the list of actions to be materialized — extremely useful for checking cron/frequency, timezone, and dataset EL expressions.

If the dry run fails, you get the same error you would have gotten at submit
time (missing property, unresolved EL variable, bad path), without polluting the
job list.

---

## 4. Submitting & running (for completeness)

```sh
# Submit only (job created in PREP state, does not start)
oozie job -config job.properties -submit

# Submit + start in one shot
oozie job -config job.properties -run

# Start a previously submitted (PREP) job
oozie job -start 0000005-260727101010101-oozie-oozi-W

# Override/define properties at the command line
oozie job -config job.properties -run -Dinput=/data/in -Dqueue=high
```

Minimal `job.properties` for EMR:

```properties
nameNode=hdfs://<master-private-dns>:8020
jobTracker=<master-private-dns>:8032
queueName=default
oozie.use.system.libpath=true
oozie.wf.application.path=${nameNode}/user/hadoop/apps/my-app
```

> `jobTracker` on YARN-era clusters is the **ResourceManager** address (port
> 8032 on EMR). A wrong value here produces `JA009`/`JA006` connection errors.

---

## 5. Inspecting a running or finished job

```sh
# List recent workflow jobs
oozie jobs                                   # workflows (default)
oozie jobs -jobtype coordinator              # coordinators
oozie jobs -jobtype bundle                   # bundles
oozie jobs -filter status=RUNNING            # filter
oozie jobs -filter "status=KILLED;status=FAILED" -len 50
oozie jobs -filter user=hadoop -len 20

# Full status of one job: every action, its state, external ID, transitions
oozie job -info 0000005-260727101010101-oozie-oozi-W

# Verbose: adds console URLs, error codes/messages per action
oozie job -info 0000005-260727101010101-oozie-oozi-W -verbose

# Info on one specific action within the workflow
oozie job -info 0000005-260727101010101-oozie-oozi-W@my-spark-node

# For coordinators: show a window of actions
oozie job -info 0000004-...-C -len 30 -order desc
oozie job -info 0000004-...-C@12          # a single coordinator action

# The exact definition the server is executing
oozie job -definition 0000005-260727101010101-oozie-oozi-W

# The fully-resolved configuration used for the job
oozie job -configcontent 0000005-260727101010101-oozie-oozi-W
```

Key things to read from `-info`:

- **Status per action** — `OK`, `ERROR`, `KILLED`, `START_RETRY`, etc.
- **Ext ID** — the YARN application ID (`application_...`) of the launcher; you need this for YARN-side log digging.
- **Error Code / Error Message** — Oozie-level failure reason (e.g. `JA018`, `E0729`).
- **Console URL** — link into the ResourceManager UI for that action.

---

## 6. Logs — the three layers

Oozie failures almost always require looking at **three** log layers, in order:

### Layer 1 — Oozie job log

```sh
# Full job log from the Oozie server
oozie job -log 0000005-260727101010101-oozie-oozi-W

# Only the audit log / error log for the job (Oozie 4.1+)
oozie job -auditlog 0000005-260727101010101-oozie-oozi-W
oozie job -errorlog 0000005-260727101010101-oozie-oozi-W

# Filter the log (by action, log level, text)
oozie job -log 0000005-...-W -action 3
oozie job -log 0000005-...-W -logfilter loglevel=ERROR
oozie job -log 0000005-...-W -logfilter "text=Exception;limit=100"
```

### Layer 2 — YARN launcher/application logs

Each Oozie action runs as a YARN application (the "launcher"), which may itself
spawn another application (e.g. the real Spark job). Get the application ID from
`oozie job -info` (the **Ext ID** column), then:

```sh
# List applications to find yours
yarn application -list -appStates ALL | grep -i oozie

# Aggregated logs for the launcher (works after the app finishes)
yarn logs -applicationId application_1753600000000_0042

# Narrow it down
yarn logs -applicationId application_..._0042 -log_files stdout
yarn logs -applicationId application_..._0042 -log_files stderr
yarn logs -applicationId application_..._0042 | grep -iA5 'exception\|error\|caused by'

# The launcher log usually names the CHILD application it spawned:
yarn logs -applicationId application_..._0042 | grep -o 'application_[0-9_]*' | sort -u
# ...then pull the child app's logs the same way.
```

> On EMR, YARN container logs are also aggregated to
> `s3://<emr-log-bucket>/<cluster-id>/containers/` (if cluster logging is
> enabled) — useful after the cluster or nodes are gone.

### Layer 3 — Oozie server logs (master node)

For server-side problems (job stuck in `PREP`, submissions rejected, DB issues):

```sh
sudo less /var/log/oozie/oozie.log
sudo grep -i 'ERROR\|WARN' /var/log/oozie/oozie.log | tail -50
grep '0000005-260727101010101' /var/log/oozie/oozie.log   # trace one job
```

---

## 7. Recovery commands: rerun, resume, kill

```sh
# Kill a job (workflow, coordinator, or bundle)
oozie job -kill 0000005-260727101010101-oozie-oozi-W

# Kill a range/scope of coordinator actions
oozie job -kill 0000004-...-C -action 3-5
oozie job -kill 0000004-...-C -date 2026-07-01T00:00Z::2026-07-10T00:00Z

# Suspend / resume
oozie job -suspend 0000005-...-W
oozie job -resume 0000005-...-W

# Rerun a workflow, skipping the nodes that already succeeded
oozie job -rerun 0000005-...-W -Doozie.wf.rerun.failnodes=true

# Rerun the whole workflow but skip specific named nodes
oozie job -rerun 0000005-...-W -Doozie.wf.rerun.skip.nodes=node1,node2

# Rerun coordinator actions (by action number or date range)
oozie job -rerun 0000004-...-C -action 3
oozie job -rerun 0000004-...-C -action 3-8
oozie job -rerun 0000004-...-C -date 2026-07-01T00:00Z::2026-07-05T00:00Z
# -refresh re-checks dataset dependencies; -nocleanup keeps old output
oozie job -rerun 0000004-...-C -action 3 -refresh
oozie job -rerun 0000004-...-C -action 3 -nocleanup

# Change a running coordinator's end time / concurrency / pause time
oozie job -change 0000004-...-C -value endtime=2026-12-31T00:00Z
oozie job -change 0000004-...-C -value concurrency=2
```

> **Rerun rule of thumb:** you must pass either `failnodes=true` **or**
> `skip.nodes` (possibly empty via config) — otherwise Oozie refuses with
> `E0401`/complains about missing rerun properties.

---

## 8. Debug switches

### CLI debug output

```sh
# Print the exact REST calls the CLI makes to the server
oozie job -info 0000005-...-W -debug

# Same via environment variable (applies to every command)
export OOZIE_DEBUG=1
```

This shows the underlying HTTP request (URL, method), which is invaluable when
the CLI errors are opaque or you're behind a proxy/load balancer.

### Action-level debugging in the workflow

- **Shell action:** add `set -x` at the top of the script; everything lands in the launcher's `stdout`/`stderr` (Layer 2 logs above).
- **Java action:** `System.out`/`System.err` go to the launcher container logs.
- **Spark action:** add `--verbose` to `<spark-opts>`; the driver log is in the child YARN application, not the launcher.
- **Hive action:** pass `-hiveconf hive.root.logger=DEBUG,console` in `<argument>` elements to fatten the launcher logs.
- **Capture output:** use `<capture-output/>` in shell/ssh/java actions and inspect it later with `oozie job -info <wf>@<action> -verbose`.

### Server-side debug logging

Raise Oozie's own log level (server-side problems only):

```sh
sudo vi /etc/oozie/conf/oozie-log4j.properties   # log4j.logger.org.apache.oozie=DEBUG, ...
sudo systemctl restart oozie
```

On EMR, prefer doing this via a reconfiguration of the `oozie-log4j`
classification so it survives node replacement.

---

## 9. The Oozie Web UI on EMR

The Oozie console runs on the master node at port `11000`. Reach it with an SSH
tunnel + SOCKS proxy (standard EMR pattern):

```sh
# Option A: dynamic port forwarding (use with a browser SOCKS proxy / FoxyProxy)
ssh -i my-key.pem -ND 8157 hadoop@<master-public-dns>
# browse to http://<master-private-dns>:11000/oozie

# Option B: plain local forward
ssh -i my-key.pem -NL 11000:localhost:11000 hadoop@<master-public-dns>
# browse to http://localhost:11000/oozie
```

The UI gives you job DAG visualization, per-action status, and click-through to
job logs — the same data as `oozie job -info/-log`, but easier to scan.

Also useful: the **YARN ResourceManager UI** at port `8088` (tunnel the same
way) to inspect launcher and child applications.

---

## 10. Common failure patterns & fixes

| Symptom / error | Likely cause | Fix |
|---|---|---|
| `E0701 XML schema error` | Malformed workflow XML, wrong element order, wrong xmlns version | `oozie validate`, fix XML; check the schema version in `xmlns` matches features used |
| `E0504 / E0505 App not found` | `oozie.wf.application.path` wrong or `workflow.xml` missing | `hdfs dfs -ls <app-path>`; the path must be a **directory** containing `workflow.xml` |
| `JA009 / JA006 Cannot connect` | Wrong `jobTracker`/`nameNode` in `job.properties` | On EMR YARN: `jobTracker=<master>:8032`, `nameNode=hdfs://<master>:8020` |
| `JA018 Launcher exception` | The action's launcher failed — real error is in YARN logs | `yarn logs -applicationId <ext-id>` (Layer 2) |
| `ClassNotFoundException` in action | Sharelib not loaded | Set `oozie.use.system.libpath=true`; verify `oozie admin -shareliblist <type>`; run `oozie admin -sharelibupdate` after changes |
| Job stuck in `PREP` | Server can't reach RM/NN, or callable queue backed up | `oozie admin -status`, check `/var/log/oozie/oozie.log`, `oozie admin -queuedump` |
| Coordinator action stuck in `WAITING` | Dataset dependency (`_SUCCESS` flag / done-flag) not present | `oozie job -info <coord>@<n> -verbose` shows the missing dependency URI; check it in HDFS/S3 |
| Coordinator fires at wrong time | Timezone confusion — Oozie times are **UTC** | Coordinator `start/end` are UTC (`Z` suffix); use `timezone` attribute only for DST-aware frequencies |
| `E0803 IO error` / DB errors | Oozie metastore (Derby by default on EMR) issues | Check `oozie.log`; consider configuring an external RDS MySQL metastore for production |
| Permission denied on app path | Files owned by wrong user | Submit as `hadoop` (or fix HDFS ownership); Oozie runs actions as the submitting user |
| Action works in CLI but fails in Oozie | Env differences — no login shell, different user, no local files | Ship every file via `<file>` / `<archive>`; never rely on the local FS of a node |

---

## 11. End-to-end pre-flight checklist

Run through this before every submission of a new/changed workflow:

```sh
# 1. XML is well-formed and schema-valid
xmllint --noout workflow.xml
oozie validate workflow.xml

# 2. App directory in HDFS is complete (workflow.xml + lib/ + scripts)
hdfs dfs -ls -R /user/hadoop/apps/my-app

# 3. Server is healthy and sharelib present
oozie admin -status
oozie admin -shareliblist

# 4. Dry run resolves all properties and EL expressions
oozie job -dryrun -config job.properties

# 5. Submit and watch
oozie job -config job.properties -run
watch -n 10 'oozie job -info <job-id> | head -40'

# 6. On any failure: Oozie log -> YARN launcher log -> child app log
oozie job -info <job-id> -verbose
oozie job -log <job-id>
yarn logs -applicationId <ext-id>
```

---

## 12. Quick command reference

| Task | Command |
|---|---|
| Server status | `oozie admin -status` |
| Validate XML | `oozie validate workflow.xml` |
| Dry run | `oozie job -dryrun -config job.properties` |
| Submit + run | `oozie job -config job.properties -run` |
| List jobs | `oozie jobs [-jobtype coordinator\|bundle] [-filter status=RUNNING]` |
| Job status | `oozie job -info <id> [-verbose]` |
| Job definition | `oozie job -definition <id>` |
| Job config | `oozie job -configcontent <id>` |
| Job log | `oozie job -log <id>` |
| Kill | `oozie job -kill <id>` |
| Suspend / resume | `oozie job -suspend <id>` / `oozie job -resume <id>` |
| Rerun failed nodes | `oozie job -rerun <id> -Doozie.wf.rerun.failnodes=true` |
| Rerun coord actions | `oozie job -rerun <coord-id> -action 3-8 [-refresh] [-nocleanup]` |
| Change coord settings | `oozie job -change <coord-id> -value endtime=...` |
| Sharelib list / refresh | `oozie admin -shareliblist` / `oozie admin -sharelibupdate` |
| CLI debug | `-debug` flag or `export OOZIE_DEBUG=1` |
| YARN action logs | `yarn logs -applicationId <ext-id>` |
| Server logs | `/var/log/oozie/oozie.log` on the master node |
