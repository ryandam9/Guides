# grep Helper — Practical Reference

A working reference for GNU grep on Linux: everyday flags, regex syntax,
recursive searching, dealing with binary files, and ready-to-use recipes
(with a bias toward log hunting on servers).

```sh
grep [options] PATTERN [file...]
```

Exit codes: `0` = match found, `1` = no match, `2` = error — handy in scripts:
`grep -q 'ERROR' app.log && echo "errors present"`.

---

## 1. The flags you use every day

| Flag | Meaning |
|---|---|
| `-i` | Case-insensitive |
| `-v` | Invert — show lines that do **NOT** match |
| `-n` | Show line numbers |
| `-c` | Count matching lines (per file) |
| `-l` | Only list **filenames** that match (`-L` = files that don't) |
| `-r` / `-R` | Recursive into directories (`-R` also follows symlinks) |
| `-w` | Match whole words only (`error` but not `errors`) |
| `-x` | Match whole lines only |
| `-o` | Print only the matched part, one per line |
| `-h` / `-H` | Hide / force the filename prefix in output |
| `-q` | Quiet — no output, exit code only |
| `-s` | Suppress "No such file / permission denied" noise |
| `-m N` | Stop after N matches (fast peek at a huge file) |
| `-e PAT` | Explicit pattern (needed when it starts with `-`, or for multiple) |
| `-f file` | Read patterns from a file, one per line |
| `--color=auto` | Highlight matches (alias it: `alias grep='grep --color=auto'`) |

```sh
grep -in 'exception' app.log            # case-insensitive, with line numbers
grep -c 'WARN' app.log                  # how many WARN lines?
grep -rl 'TODO' src/                    # which files contain TODO?
grep -vw 'DEBUG' app.log                # everything except whole-word DEBUG
grep -o 'application_[0-9_]*' launcher.log | sort -u   # extract YARN app IDs
```

---

## 2. Context around matches — `-A` / `-B` / `-C`

The single most useful thing for log debugging:

| Flag | Shows |
|---|---|
| `-A N` | N lines **After** the match |
| `-B N` | N lines **Before** the match |
| `-C N` | N lines of **Context** on both sides (same as `-A N -B N`) |

```sh
grep -A 20 'ERROR' oozie.log            # error + the 20 lines that follow
grep -B 5 -A 30 'Caused by' app.log     # stack traces with lead-in
grep -C 3 'OutOfMemoryError' *.log
```

Groups of context are separated with `--` lines. Combine with `tail` to see
just the most recent occurrence:

```sh
grep -A 30 'ERROR' oozie.log | tail -40
```

---

## 3. Multiple patterns — AND / OR / NOT

**OR** — any of several patterns:

```sh
grep -E 'ERROR|FATAL|Exception' app.log       # extended regex alternation
grep -e ERROR -e FATAL -e Exception app.log   # same, with repeated -e
```

**AND** — both patterns on the same line: chain greps:

```sh
grep 'ERROR' app.log | grep 'Oozie'           # line contains ERROR and Oozie
grep -E 'ERROR.*Oozie|Oozie.*ERROR' app.log   # single-pass alternative
```

**NOT** — match one thing, exclude another:

```sh
grep 'ERROR' app.log | grep -v 'Retrying'     # errors, minus retry noise
```

---

## 4. Regex flavors: `-G` vs `-E` vs `-F` vs `-P`

| Flag | Flavor | Notes |
|---|---|---|
| (default) | Basic (BRE) | `+ ? | ( ) { }` are **literal** unless backslashed |
| `-E` | Extended (ERE) | `+ ? | ( ) { }` work as operators — use this by default |
| `-F` | Fixed strings | No regex at all — fastest, safest for literal text |
| `-P` | Perl (PCRE) | `\d \s \b`, lookaheads, lazy `*?` — GNU grep only |

```sh
grep -F '192.168.1.10' access.log        # literal dots — no escaping needed
grep -E 'wait(ed|ing)? [0-9]+ms' app.log
grep -P '(?<=user=)\w+' app.log -o       # lookbehind: just the username
```

Regex quick reference (ERE):

| Pattern | Matches |
|---|---|
| `.` | Any single character |
| `*` / `+` / `?` | 0+ / 1+ / 0-or-1 of the previous item |
| `{3}` / `{2,5}` | Exactly 3 / between 2 and 5 |
| `^` / `$` | Start / end of line |
| `[abc]` / `[^abc]` | Any of a,b,c / anything except |
| `[0-9A-Fa-f]` | Character ranges |
| `(foo|bar)` | Alternation (grouping) |
| `\.` | A literal dot (escape regex specials: `.[]()*+?{}^$\|`) |
| `\b` | Word boundary (GNU extension; also `-w`) |
| `[[:digit:]]` `[[:alpha:]]` `[[:space:]]` | POSIX classes |

> **Quote your patterns.** Always single-quote: `grep 'a|b*'` — otherwise the
> shell expands `*`, `$`, and friends before grep ever sees them.

---

## 5. Recursive search done right

```sh
grep -rn 'pattern' .                      # everything under the current dir
grep -rn --include='*.py' 'def main' .    # only certain file types
grep -rn --include='*.{xml,properties}' 'oozie' .
grep -rn --exclude='*.log' 'pattern' .
grep -rn --exclude-dir={.git,node_modules,target,venv} 'pattern' .
grep -rnI 'pattern' .                     # -I skips binary files entirely
```

For huge trees, `find` + `xargs` parallelizes nicely:

```sh
find . -name '*.java' -print0 | xargs -0 -P 4 grep -l 'deprecated'
```

> If you do a lot of code searching, `ripgrep` (`rg`) is a drop-in upgrade:
> recursive by default, respects `.gitignore`, skips binaries, and is much
> faster. `rg 'pattern'` ≈ `grep -rnI --exclude-dir=.git 'pattern' .`

---

## 6. "Binary file matches" — what it means and what to do

When grep prints:

```
Binary file app.log matches
```

it **did** find your pattern, but the file contains bytes that make grep treat
it as binary (a NUL byte, control characters, or a non-UTF-8 encoding), so it
won't print the line. Fixes, by cause:

```sh
# Just show me the lines (file is mostly text with a few stray bytes):
grep -a 'pattern' file                # -a / --binary-files=text

# Figure out what the file actually is first:
file myfile

# Log polluted with NUL bytes (common in YARN/Oozie container logs):
tr -d '\000' < file | grep 'pattern'

# UTF-16 file (typically from Windows — `file` will say so):
iconv -f utf-16 -t utf-8 file | grep 'pattern'

# Rotated/compressed logs — don't decompress by hand:
zgrep 'pattern' app.log.3.gz          # gzip
zgrep 'pattern' /var/log/oozie/oozie.log-*.gz
bzgrep / xzgrep / zstdgrep            # bzip2 / xz / zstd variants

# Genuinely binary (jar, executable): search printable strings instead:
strings binaryfile | grep 'pattern'

# Recursive search where binaries are noise — skip them:
grep -rI 'pattern' .
```

---

## 7. Log-hunting recipes

```sh
# Errors with stack traces, most recent first-ish
grep -n -A 25 'ERROR' /var/log/oozie/oozie.log | tail -60

# All the distinct error codes in a log
grep -oE 'E[0-9]{4}|JA[0-9]{3}' oozie.log | sort | uniq -c | sort -rn

# Follow a live log but only show interesting lines
tail -f app.log | grep --line-buffered -E 'ERROR|WARN|Exception'

# Everything about one Oozie job across a huge log
grep '0000005-260727101010101-oozie-oozi-W' oozie.log | less

# Extract & count IPs hitting a server
grep -oE '[0-9]{1,3}(\.[0-9]{1,3}){3}' access.log | sort | uniq -c | sort -rn | head

# Lines within a time window (timestamps sort lexicographically)
grep -E '^2026-07-30 1[4-6]:' app.log

# Find which config file sets a property
grep -rn 'oozie.service' /etc/oozie/conf/

# Search shell history
history | grep 'spark-submit'

# Non-empty, non-comment lines of a config (see what's actually set)
grep -vE '^\s*(#|$)' /etc/oozie/conf/oozie-env.sh
```

> `--line-buffered` matters when grep sits in a pipeline after `tail -f` —
> without it, output arrives in delayed chunks.

---

## 8. Gotchas & good habits

- **`grep: warning: recursive search of stdin`** — you wrote `grep -r pattern`
  with no path; add `.` at the end.
- **Pattern starts with a dash** — use `-e`: `grep -e '-Xmx' launch.sh`
  (or `--`: `grep -- '-Xmx' launch.sh`).
- **No output but you're sure it's there** — check for: case (`-i`), the file
  being binary (section 6), CRLF line endings breaking `$` anchors
  (`file f` shows "CRLF"; strip with `tr -d '\r'`), or the text actually being
  split across lines (grep is line-based — no multiline matches without `-Pz`).
- **Whole-word surprises** — `grep error` matches `terror`; use `-w`.
- **Searching for a regex special literally** — prefer `-F` over escaping.
- **Slow recursive grep** — add `-I` (skip binaries), `--exclude-dir` for
  `.git`/build dirs, or switch to `rg`.
- **In scripts** prefer `grep -q` for existence tests, and remember exit code
  `1` just means "not found" — don't treat it as a failure with `set -e`:
  `grep -q pat file || true`.
- `egrep`/`fgrep` are deprecated spellings of `grep -E` / `grep -F`.

---

## 9. Quick reference card

```
MATCHING                        OUTPUT                       SCOPE
-i  ignore case                 -n  line numbers             -r  recursive
-w  whole words                 -c  count lines              --include='*.py'
-x  whole lines                 -l  filenames only           --exclude-dir=.git
-v  invert match                -o  matched text only        -I  skip binaries
-E  extended regex              -A/-B/-C N  context          -m N stop after N
-F  literal strings             -H/-h  show/hide filename
-P  perl regex (\d \b ...)      -q  quiet (exit code)        BINARY FILES
-e/-f  pattern(s) from arg/file --color=auto  highlight      -a  force as text
                                                             zgrep  .gz logs
                                                             strings f | grep
```
