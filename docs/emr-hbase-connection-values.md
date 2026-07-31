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

## 4. Putting it together — a client connection block

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

## 5. One-shot summary script

Run on the master or an edge node — prints all values, already extracted:

```sh
echo "EMR master host : $(hdfs getconf -confKey fs.defaultFS 2>/dev/null | sed -E 's#hdfs://([^:/]+).*#\1#')"
echo "ZK quorum       : $(xmllint --xpath "//property[name='hbase.zookeeper.quorum']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null)"
echo "ZK client port  : $(xmllint --xpath "//property[name='hbase.zookeeper.property.clientPort']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null || echo 2181)"
echo "znode parent    : $(xmllint --xpath "//property[name='zookeeper.znode.parent']/value/text()" /etc/hbase/conf/hbase-site.xml 2>/dev/null || echo /hbase)"
echo "HBase master    : $(echo 'status "simple"' | hbase shell -n 2>/dev/null | awk '/active master:/ {print $3}')"
```

Sample run:

```
EMR master host : ip-10-0-1-23.ec2.internal
ZK quorum       : ip-10-0-1-23.ec2.internal
ZK client port  : 2181
znode parent    : /hbase
HBase master    : ip-10-0-1-23.ec2.internal:16000
```

---

## 6. No login to the master? Use an edge node

Every command above except `systemctl`/`hostname -f`/`job-flow.json` works
from an edge node — the client configs there point at the master by
definition. If you need an actual shell on the master and direct SSH fails:

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
