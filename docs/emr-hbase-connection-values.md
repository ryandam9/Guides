# Finding HBase / EMR Connection Values — and Reading Them Out of the Output

How to fetch the three values every HBase client asks for on an Amazon EMR
cluster — **HBase ZooKeeper quorum**, **EMR master host**, and **HBase (HMaster)
host** — with annotated sample outputs so you know exactly *which part of the
output is the value*.

> **The short version.** On EMR, all three usually point at the same machine:
> the EMR **primary (master) node**. The ZooKeeper quorum is the master's
> private DNS name, the HMaster runs on the master node, and the NameNode /
> ResourceManager / Oozie all live there too. Multi-master EMR clusters are the
> exception (three masters → three quorum hosts).

| Value | Authoritative source | Typical EMR value |
|---|---|---|
| `hbase.zookeeper.quorum` | `/etc/hbase/conf/hbase-site.xml` | `ip-10-0-1-23.ec2.internal` |
| ZooKeeper client port | same file (`hbase.zookeeper.property.clientPort`) | `2181` |
| EMR master host | `hdfs getconf -confKey fs.defaultFS` or `job-flow.json` | `ip-10-0-1-23.ec2.internal` |
| HBase HMaster host | `hbase shell` → `status` / HBase UI `:16010` | same as master node |
| `zookeeper.znode.parent` | `hbase-site.xml` | `/hbase` |
| HBase Kerberos principal | `hbase-site.xml` (secured clusters only) | `hbase/_HOST@EC2.INTERNAL` |
| Thrift URL (`thrift_url`) | master host + port 9090 (`hbase-thrift` daemon) | `http://ip-10-0-1-23.ec2.internal:9090` |
| NameNode (`nameNode=`) | `hdfs getconf -confKey fs.defaultFS` | `hdfs://ip-10-0-1-23.ec2.internal:8020` |
| ResourceManager (`jobTracker=`) | `yarn-site.xml` host + port `8032` | `ip-10-0-1-23.ec2.internal:8032` |

Everything below works from the **master node or any edge node** that has the
client configs (`/etc/hbase/conf`, `/etc/hadoop/conf`) — no login to the master
required, except where noted.

---

## 1. HBase ZooKeeper quorum

### 1a. Straight from `hbase-site.xml` (most reliable)

```sh
grep -A2 'hbase.zookeeper.quorum' /etc/hbase/conf/hbase-site.xml
```

Sample output — **the value is the text inside `<value>...</value>` on the
line after the property name**:

```xml
  <property>
    <name>hbase.zookeeper.quorum</name>
    <value>ip-10-0-1-23.ec2.internal</value>      ← THIS is your quorum
  </property>
```

On a **multi-master** EMR cluster you'll see three hosts, comma-separated —
the whole comma-separated string is the quorum, keep it intact:

```xml
    <value>ip-10-0-1-23.ec2.internal,ip-10-0-1-24.ec2.internal,ip-10-0-1-25.ec2.internal</value>
```

Get the client port the same way (if the property is absent, the default
`2181` applies):

```sh
grep -A2 'hbase.zookeeper.property.clientPort' /etc/hbase/conf/hbase-site.xml
```

### 1b. Value only, no XML noise

Either of these prints the bare value — nothing to interpret:

```sh
# XPath — prints just: ip-10-0-1-23.ec2.internal
xmllint --xpath "//property[name='hbase.zookeeper.quorum']/value/text()" \
    /etc/hbase/conf/hbase-site.xml; echo

# Let HBase resolve it (includes defaults if the property isn't in the file)
hbase org.apache.hadoop.hbase.util.HBaseConfTool hbase.zookeeper.quorum
hbase org.apache.hadoop.hbase.util.HBaseConfTool hbase.zookeeper.property.clientPort
hbase org.apache.hadoop.hbase.util.HBaseConfTool zookeeper.znode.parent
```

> `HBaseConfTool` may print a few log4j/INFO lines first. **The value is the
> last line of output** — a bare hostname (or `2181` / `/hbase`), with no
> timestamp or log level in front of it.

### 1c. Verify the quorum actually answers

```sh
echo ruok | nc ip-10-0-1-23.ec2.internal 2181
```

Output is exactly four characters — `imok` — nothing else. If you get silence
or "connection refused", the host/port is wrong or a security group is in the
way. For more detail:

```sh
echo srvr | nc ip-10-0-1-23.ec2.internal 2181
```

```
Zookeeper version: 3.5.10-...                  ← ZK is alive
Latency min/avg/max: 0/0/23
Mode: standalone                               ← "standalone" on 1-master EMR,
Node count: 512                                   "leader"/"follower" on multi-master
```

---

## 2. EMR master host

### 2a. From Hadoop config — `fs.defaultFS` (works on any node)

```sh
hdfs getconf -confKey fs.defaultFS
```

Output is one line; **the master host is the part between `hdfs://` and the
`:8020` port**:

```
hdfs://ip-10-0-1-23.ec2.internal:8020
        └──────────┬────────────┘
                   └── EMR master host (private DNS)
```

Strip it in one go if you want just the hostname:

```sh
hdfs getconf -confKey fs.defaultFS | sed -E 's#hdfs://([^:/]+).*#\1#'
```

### 2b. From EMR instance metadata (EMR-managed nodes only)

```sh
grep masterPrivateDnsName /mnt/var/lib/info/job-flow.json
# older AMIs: /emr/instance-controller/lib/info/job-flow.json
```

Output — **the value is the quoted string after the colon**:

```json
  "masterPrivateDnsName": "ip-10-0-1-23.ec2.internal",
                           └──────────┬─────────────┘
                                      └── EMR master host
```

> This file exists only on nodes EMR itself manages (master/core/task). A
> custom edge node won't have it — use method 2a there.

### 2c. From outside the cluster — AWS CLI

```sh
aws emr describe-cluster --cluster-id j-1K2L3M4N5O6P7 \
    --query 'Cluster.MasterPublicDnsName' --output text
```

Output is a single line, already the answer (public DNS — use this for SSH
from your laptop):

```
ec2-54-210-11-22.compute-1.amazonaws.com
```

For the **private** DNS and IP (what cluster-internal configs use):

```sh
aws emr list-instances --cluster-id j-1K2L3M4N5O6P7 \
    --instance-group-types MASTER \
    --query 'Instances[].{PrivateDns:PrivateDnsName,PrivateIp:PrivateIpAddress}' \
    --output table
```

```
---------------------------------------------------
|                  ListInstances                  |
+---------------------------+---------------------+
|         PrivateDns        |      PrivateIp      |
+---------------------------+---------------------+
|  ip-10-0-1-23.ec2.internal|  10.0.1.23          |   ← master host / IP
+---------------------------+---------------------+
```

(Don't know the cluster ID? `aws emr list-clusters --active` — the `Id`
column, `j-...`.)

### 2d. Cross-checks that should all agree

All of these point at the master; if one disagrees, you're reading the wrong
cluster's config:

```sh
grep -A2 'yarn.resourcemanager.hostname' /etc/hadoop/conf/yarn-site.xml
# <value>ip-10-0-1-23.ec2.internal</value>              ← same host

hostname -f          # run ON the master itself → prints the same private DNS
```

---

## 3. HBase (HMaster) host

On EMR the HMaster runs **on the master node**, so in practice this equals the
value from section 2. Confirm it from the live cluster:

### 3a. `hbase shell` status

```sh
echo 'status' | hbase shell -n 2>/dev/null
```

Sample output — read it line by line:

```
1 active master, 0 backup masters, 3 servers, 0 dead, 217.0000 average load
│                                  │
│                                  └── 3 RegionServers (your core nodes)
└── exactly one active HMaster — good
```

To see *which host* is the active master and which are RegionServers:

```sh
echo 'status "simple"' | hbase shell -n 2>/dev/null | head -15
```

```
active master:  ip-10-0-1-23.ec2.internal:16000 1785400000000
                └──────────┬─────────────┘
                           └── HBase (HMaster) host, RPC port 16000
0 backupMasters
3 live servers
    ip-10-0-2-11.ec2.internal:16020 ...        ← RegionServers (core nodes)
    ip-10-0-2-12.ec2.internal:16020 ...
    ip-10-0-2-13.ec2.internal:16020 ...
```

> Ignore the long number after the port (a start timestamp) and all the
> `requestsPerSecond=...` metrics after each server — you only need the
> `host:port` at the start of each line.

### 3b. Process check (on the master node itself)

```sh
sudo systemctl status hbase-master
```

```
● hbase-master.service - HBase master daemon
     Active: active (running) since Thu 2026-07-31 01:10:12 UTC; 3h ago
             └── "active (running)" is what you're looking for
```

`jps` works too — look for `HMaster` in the list (RegionServers show as
`HRegionServer` on core nodes).

### 3c. Web UI

The HBase UI on the master node, port **16010** (SSH tunnel required, same as
any EMR UI): `http://<master-private-dns>:16010`. The front page shows the
active master, backup masters, and the RegionServer list.

---

## 4. HBase Kerberos principal (secured clusters only)

If the cluster uses Kerberos (an EMR **security configuration** with Kerberos
enabled), clients also need the HBase service principals. If it doesn't, the
properties below simply won't exist in the file — that itself is your answer
(no principal needed).

### 4a. From `hbase-site.xml`

```sh
grep -B1 -A2 'kerberos.principal' /etc/hbase/conf/hbase-site.xml
```

Sample output — **the value is the `<value>` line under each property name**:

```xml
  <property>
    <name>hbase.master.kerberos.principal</name>
    <value>hbase/_HOST@EC2.INTERNAL</value>        ← HMaster principal
  </property>
  <property>
    <name>hbase.regionserver.kerberos.principal</name>
    <value>hbase/_HOST@EC2.INTERNAL</value>        ← RegionServer principal
  </property>
```

How to read `hbase/_HOST@EC2.INTERNAL`:

```
hbase   /   _HOST   @   EC2.INTERNAL
└─┬─┘       └─┬─┘       └─────┬────┘
service    placeholder      realm
user       replaced by each
           server's own FQDN
```

- **Keep `_HOST` literal in client configs** — the client substitutes the
  actual server hostname at connection time. Do NOT replace it by hand.
- The **realm** (after `@`) varies: EMR's cluster-dedicated KDC typically uses
  a realm like `EC2.INTERNAL`; a corporate/cross-realm setup shows your
  AD/MIT realm (e.g. `CORP.EXAMPLE.COM`).

Bare-value one-liners, same as before:

```sh
xmllint --xpath "//property[name='hbase.master.kerberos.principal']/value/text()" \
    /etc/hbase/conf/hbase-site.xml; echo
hbase org.apache.hadoop.hbase.util.HBaseConfTool hbase.master.kerberos.principal
```

### 4b. Confirm the realm from `krb5.conf`

```sh
grep default_realm /etc/krb5.conf
```

```
 default_realm = EC2.INTERNAL          ← the realm part of every principal
```

### 4c. From the keytab (on the master node, needs sudo)

The service keytab lists the exact principals it holds — no `_HOST`
placeholder, fully resolved:

```sh
sudo klist -kt /etc/hbase.keytab
```

```
Keytab name: FILE:/etc/hbase.keytab
KVNO Timestamp           Principal
---- ------------------- ------------------------------------------------------
   2 07/31/2026 01:10:11 hbase/ip-10-0-1-23.ec2.internal@EC2.INTERNAL   ← real
   2 07/31/2026 01:10:11 hbase/ip-10-0-1-23.ec2.internal@EC2.INTERNAL      principal,
   ...                                                                      repeated once
                                                                            per encryption type
```

> The same principal appearing on multiple lines is normal — one entry per
> encryption type (and per KVNO after rekeys). It's still one principal.

### 4d. What a client needs on a Kerberized cluster

```properties
hbase.security.authentication=kerberos
hbase.master.kerberos.principal=hbase/_HOST@EC2.INTERNAL
hbase.regionserver.kerberos.principal=hbase/_HOST@EC2.INTERNAL
```

...and a valid ticket before connecting (`kinit your-user@REALM`, or
`kinit -kt your.keytab principal` for services). Check what you currently
hold with `klist`:

```
Ticket cache: FILE:/tmp/krb5cc_1000
Default principal: hadoop@EC2.INTERNAL     ← who YOU are authenticated as
Valid starting     Expires            Service principal
07/31/26 02:00:00  07/31/26 12:00:00  krbtgt/EC2.INTERNAL@EC2.INTERNAL
                   └── if this is in the past, kinit again
```

---

## 5. HBase Thrift server URL (`thrift_url`)

Some clients (Hue, HappyBase/Python, PHP/Ruby libs) don't speak the native
HBase RPC — they go through the **HBase Thrift server**, which EMR runs on the
master node. Its URL is:

```
http://<master-private-dns>:9090        e.g. http://ip-10-0-1-23.ec2.internal:9090
       └─────────┬────────┘ └┬─┘
                 │            └── Thrift port — default 9090
                 └── the EMR master host from section 2
```

### 5a. Confirm the Thrift server is running (master node)

```sh
sudo systemctl status hbase-thrift
```

```
● hbase-thrift.service - HBase Thrift daemon
     Active: active (running) since Thu 2026-07-31 01:10:14 UTC; 5h ago
             └── this is what you're looking for
```

If the unit doesn't exist or is inactive, the Thrift server isn't running on
this cluster — start it (`sudo systemctl start hbase-thrift`) or provision it
via the cluster config.

### 5b. Confirm the port

Defaults are **9090** (Thrift service) and **9095** (its info/status web UI).
Check for overrides first — if these properties are absent from the file, the
defaults apply:

```sh
grep -B1 -A2 'thrift' /etc/hbase/conf/hbase-site.xml
```

```xml
  <property>
    <name>hbase.regionserver.thrift.port</name>
    <value>9090</value>                      ← Thrift port (only if overridden)
  </property>
  <property>
    <name>hbase.regionserver.thrift.http</name>
    <value>true</value>                      ← transport mode, see below
  </property>
```

Then verify something is actually listening:

```sh
sudo ss -tlnp | grep -E ':(9090|9095)\b'
```

```
LISTEN 0  50  *:9090  *:*  users:(("java",pid=4567,fd=512))   ← Thrift service
LISTEN 0  50  *:9095  *:*  users:(("java",pid=4567,fd=520))   ← Thrift web UI
```

Quick sanity check from any node: `curl -s http://<master>:9095 | head` should
return the UI's HTML (the 9095 UI answering proves the daemon is up).

### 5c. Which form of `thrift_url` to use

The `hbase.regionserver.thrift.http` property (section 5b) decides the
transport, and clients must match it:

| `thrift.http` | Transport | What the client needs |
|---|---|---|
| absent / `false` | Binary Thrift socket | host + port pair: `ip-10-0-1-23.ec2.internal`, `9090` (HappyBase default) |
| `true` | Thrift-over-HTTP | full URL: `http://ip-10-0-1-23.ec2.internal:9090` (Hue's `thrift_url`; Kerberized clusters typically use this + SPNEGO) |

> Thrift protocol version matters too: `hbase-thrift` is the Thrift1 API
> (HappyBase, Hue). The separate `hbase-thrift2` daemon speaks the newer
> Thrift2 API — different, incompatible clients. On EMR you'll normally only
> find `hbase-thrift`.

---

## 6. NameNode and ResourceManager addresses

Both daemons run on the EMR master node. The standard EMR ports:

| Daemon | RPC (clients/jobs) | Web UI |
|---|---|---|
| HDFS NameNode | `8020` | `9870` |
| YARN ResourceManager | `8032` | `8088` |

### 6a. NameNode

```sh
hdfs getconf -confKey fs.defaultFS
```

```
hdfs://ip-10-0-1-23.ec2.internal:8020
        └──────────┬────────────┘ └┬─┘
                   │               └── NameNode RPC port
                   └── NameNode host (= EMR master)
```

The whole string is what jobs use (e.g. `nameNode=` in an Oozie
`job.properties`). For the web UI address:

```sh
hdfs getconf -confKey dfs.namenode.http-address
```

```
ip-10-0-1-23.ec2.internal:9870        ← NameNode UI → http://ip-10-0-1-23.ec2.internal:9870
```

> If this prints `0.0.0.0:9870`, the daemon listens on all interfaces — the
> host to use is still the master host from section 2; only take the **port**
> from this output.

Verify it's alive and which state it's in:

```sh
hdfs dfsadmin -report | head -8
```

```
Configured Capacity: 3298534883328 (3.00 TB)
Present Capacity: 3200000000000
DFS Remaining: 3100000000000            ← numbers = NameNode is answering
...
Live datanodes (3):                     ← your core nodes are registered
```

### 6b. ResourceManager

```sh
grep -A2 'yarn.resourcemanager.hostname' /etc/hadoop/conf/yarn-site.xml
```

```xml
  <property>
    <name>yarn.resourcemanager.hostname</name>
    <value>ip-10-0-1-23.ec2.internal</value>     ← RM host (= EMR master)
  </property>
```

Derive the addresses from it — RPC is `<host>:8032` (this is the `jobTracker=`
value in an Oozie `job.properties`), web UI is `http://<host>:8088`. If a full
address is configured explicitly, it wins — check:

```sh
grep -A2 'yarn.resourcemanager.address' /etc/hadoop/conf/yarn-site.xml
```

```xml
    <value>ip-10-0-1-23.ec2.internal:8032</value>   ← host:port, use as-is
```

Verify the RM is answering (works from any node):

```sh
yarn node -list 2>/dev/null
```

```
Total Nodes:3                                            ← RM answered
         Node-Id             Node-State  Node-Http-Address  Number-of-Running-Containers
ip-10-0-2-11.ec2.internal:8041  RUNNING  ip-10-0-2-11.ec2.internal:8042  4
ip-10-0-2-12.ec2.internal:8041  RUNNING  ...              ← core/task nodes
```

Or hit the REST API — one line of JSON, no SSH tunnel needed from inside the
VPC:

```sh
curl -s http://ip-10-0-1-23.ec2.internal:8088/ws/v1/cluster/info
```

```json
{"clusterInfo":{"state":"STARTED","haState":"ACTIVE",...}}
                         └── STARTED + ACTIVE = healthy RM
```

---

## 7. Putting it together — a client connection block

With the values identified above, a typical client config (Java properties /
Spark / Phoenix / NiFi etc.) looks like:

```properties
hbase.zookeeper.quorum=ip-10-0-1-23.ec2.internal
hbase.zookeeper.property.clientPort=2181
zookeeper.znode.parent=/hbase
```

Three rules of thumb:

1. Clients connect through **ZooKeeper**, not the HMaster directly — quorum +
   port + znode.parent is the complete set; you rarely need the HMaster host
   in client config at all.
2. Use the **private** DNS names inside the VPC; the public DNS is only for
   SSH/tunnels from outside.
3. Trust `/etc/hbase/conf/hbase-site.xml` over anything reconstructed by
   hand — EMR configuration classifications (`hbase-site` overrides) land in
   that file.

---

## 8. One-shot summary script

Run on the master or an edge node — prints all values, already extracted:

```sh
echo "EMR master host : $(hdfs getconf -confKey fs.defaultFS 2>/dev/null | sed -E 's#hdfs://([^:/]+).*#\1#')"
echo "ZK quorum       : $(xmllint --xpath "//property[name='hbase.zookeeper.quorum']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null)"
echo "ZK client port  : $(xmllint --xpath "//property[name='hbase.zookeeper.property.clientPort']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null || echo 2181)"
echo "znode parent    : $(xmllint --xpath "//property[name='zookeeper.znode.parent']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null || echo /hbase)"
echo "HBase master    : $(echo 'status "simple"' | hbase shell -n 2>/dev/null | awk '/active master:/ {print $3}')"
echo "HBase principal : $(xmllint --xpath "//property[name='hbase.master.kerberos.principal']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null || echo '(not kerberized)')"
_m=$(hdfs getconf -confKey fs.defaultFS 2>/dev/null | sed -E 's#hdfs://([^:/]+).*#\1#')
_tp=$(xmllint --xpath "//property[name='hbase.regionserver.thrift.port']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null || echo 9090)
echo "Thrift URL      : http://${_m}:${_tp}"
echo "NameNode        : $(hdfs getconf -confKey fs.defaultFS 2>/dev/null)"
echo "ResourceManager : $(xmllint --xpath "//property[name='yarn.resourcemanager.hostname']/value/text()" /etc/hadoop/conf/yarn-site.xml 2>/dev/null):8032"
```

Sample run:

```
EMR master host : ip-10-0-1-23.ec2.internal
ZK quorum       : ip-10-0-1-23.ec2.internal
ZK client port  : 2181
znode parent    : /hbase
HBase master    : ip-10-0-1-23.ec2.internal:16000
HBase principal : hbase/_HOST@EC2.INTERNAL
Thrift URL      : http://ip-10-0-1-23.ec2.internal:9090
NameNode        : hdfs://ip-10-0-1-23.ec2.internal:8020
ResourceManager : ip-10-0-1-23.ec2.internal:8032
```

---

## 9. No login to the master? Everything from a gateway/edge node

You do NOT need a shell on the master for any of the values in this guide.
A gateway node has copies of the client configs (`/etc/hbase/conf`,
`/etc/hadoop/conf`) that point at the master by definition, and the services
answer over the network. Here is every value with its **gateway-only** command:

| Value | Gateway-node command | Section |
|---|---|---|
| ZK quorum / port / znode | `grep -A2 'hbase.zookeeper' /etc/hbase/conf/hbase-site.xml` | 1a |
| ZK alive? | `echo ruok \| nc <quorum-host> 2181` → `imok` | 1c |
| EMR master host | `hdfs getconf -confKey fs.defaultFS` | 2a |
| HBase (HMaster) host | `echo 'status "simple"' \| hbase shell -n` (connects via ZK) | 3a |
| Kerberos principal | `grep -A2 'kerberos.principal' /etc/hbase/conf/hbase-site.xml` | 4a |
| Kerberos realm | `grep default_realm /etc/krb5.conf` | 4b |
| Thrift port config | `grep -A2 'thrift' /etc/hbase/conf/hbase-site.xml` | 5b |
| Thrift alive? | `nc -zv <master-host> 9090` and `curl -s http://<master-host>:9095 \| head` | below |
| NameNode | `hdfs getconf -confKey fs.defaultFS` | 6a |
| NameNode alive? | `hdfs dfsadmin -report \| head` | 6a |
| ResourceManager | `grep -A2 'resourcemanager.hostname' /etc/hadoop/conf/yarn-site.xml` | 6b |
| RM alive? | `yarn node -list` or `curl -s http://<master-host>:8088/ws/v1/cluster/info` | 6b |

The **one-shot script in section 8 also runs unchanged on a gateway node** —
every command in it is client-side.

**Remote substitutes for the three master-only steps:**

- `systemctl status hbase-thrift` (5a) → probe the ports from the gateway
  instead; a listener answering IS the daemon running:
  ```sh
  nc -zv ip-10-0-1-23.ec2.internal 9090
  # Connection to ip-10-0-1-23.ec2.internal 9090 port [tcp/*] succeeded!   ← running
  curl -s http://ip-10-0-1-23.ec2.internal:9095 | head -3                  # Thrift UI HTML
  ```
- `sudo klist -kt /etc/hbase.keytab` (4c) → not needed: the principal from
  `hbase-site.xml` (4a) is the same value; the keytab was only a cross-check.
- `hostname -f` / `job-flow.json` (2b) → use `hdfs getconf -confKey
  fs.defaultFS` (2a) or the AWS CLI (2c); `job-flow.json` only exists on
  EMR-managed nodes.

**Two gateway prerequisites to check if commands fail:**

1. The configs actually exist: `ls /etc/hbase/conf/hbase-site.xml
   /etc/hadoop/conf/yarn-site.xml`. If the gateway doesn't have them, copy
   them from another client node, or pull the effective values with the AWS
   CLI (2c) — `aws emr describe-cluster` also lists configuration
   classifications under `Cluster.Configurations`.
2. On a Kerberized cluster, get a ticket first (`kinit your-user@REALM`) —
   otherwise `hbase shell`, `hdfs`, and `yarn` commands fail with
   `GSSException: No valid credentials provided`, which looks like a
   connectivity problem but isn't.

If you ever do need an actual shell on the master and direct SSH fails:

```sh
# Jump through the edge node (intra-VPC SSH is usually allowed):
ssh -A your-user@<edge-node>          # -A forwards your SSH agent
ssh hadoop@ip-10-0-1-23.ec2.internal  # user is 'hadoop' on EMR, not ec2-user

# Or, with SSM permissions on the instance profile — no SSH at all:
aws ssm start-session --target <master-instance-id>
```

Server log files (`/var/log/hbase/`, `/var/log/hadoop-hdfs/`) do need the
master — or read them via the web UIs / the cluster's S3 log bucket
(`s3://<log-bucket>/<cluster-id>/node/<master-instance-id>/applications/`).
