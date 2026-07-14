#!/usr/bin/env bash
# Terminal / HTML5 gateway bootstrap (minified variant)
# Same as terminal-bootstrap.sh but without Vim, tmux, and Hadoop
# (Hive/Beeline, YARN, Oozie, HBase) support.
# 8-color safe. No sudo required.
# Recommended usage: source ./terminal-bootstrap-min.sh
# Safe behaviour: preserves existing dotfiles, backs them up (refusing to
# modify a file whose backup failed), validates managed-block markers before
# touching a file, replaces dotfiles atomically with their permissions
# preserved, and only adds/replaces managed blocks.
# Repeat runs are idempotent: unchanged blocks/files are left alone.

if [ -z "${BASH_VERSION:-}" ]; then
  echo "ERROR: terminal-bootstrap-min.sh must be run with Bash." >&2
  echo "Use one of these:" >&2
  echo "  bash ./scripts/terminal-bootstrap-min.sh --dry-run" >&2
  echo "  bash ./scripts/terminal-bootstrap-min.sh" >&2
  echo "For current-shell prompt/aliases, start Bash first, then source it:" >&2
  echo "  bash" >&2
  echo "  source ./scripts/terminal-bootstrap-min.sh" >&2
  return 1 2>/dev/null || exit 1
fi

# Remember the caller's errexit state so sourcing restores it on every exit path.
case $- in *e*) TB_HAD_ERREXIT=1 ;; *) TB_HAD_ERREXIT=0 ;; esac
set +e

TB_VERSION="1.4.0-min"

TB_ERRORS=0
TB_WARNINGS=0
TB_DRY_RUN=0
TB_UNINSTALL=0
TB_FAKE_HOME=0
TB_BACKUP_KEEP=5
TB_LOG_MAX_BYTES=512000
TB_ORIGINAL_HOME="${HOME:-}"
TB_HOME="${HOME:-}"
# Unpredictable temp log (mktemp creates it 0600); predictable name only as a
# last resort when mktemp is unavailable.
TB_INITIAL_LOG="$(mktemp "${TMPDIR:-/tmp}/terminal-bootstrap.XXXXXXXX" 2>/dev/null)"
[ -n "$TB_INITIAL_LOG" ] || TB_INITIAL_LOG="${TMPDIR:-/tmp}/terminal-bootstrap.$(id -un 2>/dev/null || echo unknown).$$.log"
TB_LOG="$TB_INITIAL_LOG"

is_sourced() { [ "${BASH_SOURCE[0]}" != "$0" ]; }
restore_shell_opts() { [ "${TB_HAD_ERREXIT:-0}" = 1 ] && set -e; return 0; }
ts() { date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date; }
log() { local level="$1"; shift; printf '%s [%s] %s\n' "$(ts)" "$level" "$*" | tee -a "$TB_LOG" >/dev/null; }
info() { log INFO "$@"; }
warn() { TB_WARNINGS=$((TB_WARNINGS+1)); log WARN "$@"; }
err() { TB_ERRORS=$((TB_ERRORS+1)); log ERROR "$@"; }
finish() {
  local code="$1"
  if is_sourced; then restore_shell_opts; return "$code"; else exit "$code"; fi
}

for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) TB_DRY_RUN=1 ;;
    --uninstall) TB_UNINSTALL=1 ;;
    --version|-V)
      echo "terminal-bootstrap-min v$TB_VERSION"
      restore_shell_opts
      return 0 2>/dev/null || exit 0
      ;;
    --help|-h)
      cat <<'HELP'
Usage:
  source ./terminal-bootstrap-min.sh [--dry-run]
  bash   ./terminal-bootstrap-min.sh [--dry-run]
  bash   ./terminal-bootstrap-min.sh --uninstall [--dry-run]
  bash   ./terminal-bootstrap-min.sh --version

Recommended:
  source ./terminal-bootstrap-min.sh

This is the minified variant: no Vim, tmux, or Hadoop (Hive/Beeline,
YARN, Oozie, HBase) support. Use terminal-bootstrap.sh for the full set.

Safety:
  - No sudo.
  - No system files changed.
  - Existing dotfiles are backed up before modification (last 5 backups
    kept); a file whose backup fails is not modified.
  - Managed-block markers are validated before a file is touched; files
    with unbalanced or duplicate markers are refused, never repaired.
  - Dotfiles are replaced atomically, preserving their permissions.
  - Existing .bashrc/.inputrc content is preserved.
  - Only managed TERMINAL_BOOTSTRAP blocks are replaced on repeat runs,
    and only when their content actually changed.
  - A fallback (fake) home is only adopted when it is a real directory
    owned by the current user, or can be created fresh with mode 0700.
  - Dry-run changes nothing, including the current shell's HOME.
  - Generated setup files under $HOME may be overwritten:
    .terminal-bootstrap-theme.sh and activate-terminal-bootstrap.sh.

Uninstall:
  --uninstall removes the managed blocks from .bashrc/.inputrc and
  deletes the generated theme/activation files.
  Backups and the log file are kept. Exit status is non-zero when any
  step failed.

Local time:
  - The prompt and time helpers use TERMINAL_BOOTSTRAP_TZ.
  - Default: Australia/Melbourne.
  - Override before sourcing, for example:
      export TERMINAL_BOOTSTRAP_TZ=Asia/Kolkata
      source ./terminal-bootstrap-min.sh

Prompt layout:
  - Default: one-line prompt.
  - To use the old multi-line prompt:
      export TERMINAL_BOOTSTRAP_PROMPT_LAYOUT=multiline
      source ./terminal-bootstrap-min.sh
  - Slow-command duration shows for commands taking >= 5s;
    tune with TERMINAL_BOOTSTRAP_SLOW_SECS, disable the timer with
    TERMINAL_BOOTSTRAP_TIMER=0.
  - The prompt IP refreshes every TERMINAL_BOOTSTRAP_IP_TTL seconds
    (default 60).

Note:
  This script requires Bash. If your login shell is sh/ksh/csh, start Bash first.
HELP
      restore_shell_opts
      return 0 2>/dev/null || exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Use --help for usage." >&2
      restore_shell_opts
      return 2 2>/dev/null || exit 2
      ;;
  esac
done

cmd_check() {
  command -v "$1" >/dev/null 2>&1 && info "command OK: $1" || warn "command missing: $1"
}

file_size() { wc -c < "$1" 2>/dev/null | tr -d ' '; }

writable_dir() {
  local dir="$1" test_file
  [ -n "$dir" ] && [ "$dir" != "/" ] && [ -d "$dir" ] && [ -w "$dir" ] || return 1
  test_file="$dir/.terminal-bootstrap-write-test.$$"
  : > "$test_file" 2>/dev/null || return 1
  rm -f "$test_file" 2>/dev/null
  return 0
}

prune_backups() {
  local file="$1" old
  ls -1t "$file".backup.* 2>/dev/null | tail -n +$((TB_BACKUP_KEEP + 1)) | while IFS= read -r old; do
    rm -f "$old" 2>/dev/null && info "pruned old backup: $old"
  done
}

# Returns non-zero when the backup could not be created; callers must then
# refuse to modify the file.
backup_file() {
  local file="$1" backup
  [ "$TB_DRY_RUN" -eq 1 ] && { info "DRY-RUN: would backup $file if it exists"; return 0; }
  [ -f "$file" ] || return 0
  backup="$file.backup.$(date +%Y%m%d_%H%M%S 2>/dev/null || date +%s)"
  if cp -p "$file" "$backup" 2>/dev/null; then
    info "backup: $file -> $backup"
    prune_backups "$file"
    return 0
  fi
  err "backup failed: $file"
  return 1
}

choose_home_base() {
  # $PWD is the last resort so a fallback home never lands inside a
  # repository checkout by surprise.
  local dir
  for dir in "${TERMINAL_BOOTSTRAP_HOME_BASE:-}" /var/tmp /tmp /apps /app /data /opt "$PWD"; do
    [ -n "$dir" ] || continue
    writable_dir "$dir" && { printf '%s\n' "$dir"; return 0; }
  done
  return 1
}

# Adopt an existing fallback-home directory only when it is safe: a real
# directory (not a symlink) owned by the current user, locked to 0700.
# Anything else on a shared host could be a pre-created trap.
secure_fake_home() {
  local dir="$1"
  if [ -L "$dir" ]; then
    err "refusing fake HOME: $dir is a symlink"
    return 1
  fi
  if [ -d "$dir" ]; then
    if [ ! -O "$dir" ]; then
      err "refusing fake HOME: $dir exists but is not owned by uid $(id -u)"
      return 1
    fi
    chmod 700 "$dir" 2>/dev/null || { err "cannot chmod 700 existing $dir"; return 1; }
  elif [ -e "$dir" ]; then
    err "refusing fake HOME: $dir exists and is not a directory"
    return 1
  else
    (umask 077; mkdir "$dir") 2>/dev/null || { err "cannot create fake HOME=$dir"; return 1; }
  fi
  writable_dir "$dir" || { err "fake HOME not writable: $dir"; return 1; }
  return 0
}

setup_home() {
  info "user=$(id -un 2>/dev/null || echo unknown) uid=$(id -u 2>/dev/null || echo unknown)"
  info "initial HOME=${HOME:-<empty>} PWD=$PWD SHELL=${SHELL:-<empty>} TERM=${TERM:-<empty>}"
  getent passwd "$(id -un 2>/dev/null)" >/dev/null 2>&1 && info "passwd=$(getent passwd "$(id -un)")" || warn "getent passwd failed"

  if writable_dir "${HOME:-}"; then
    TB_HOME="$HOME"
    info "using existing writable HOME=$HOME"
  else
    warn "HOME is missing or not writable: ${HOME:-<empty>}"
    local base new_home
    base="$(choose_home_base)"
    if [ -z "$base" ]; then
      err "no writable directory found; tried TERMINAL_BOOTSTRAP_HOME_BASE, /var/tmp, /tmp, /apps, /app, /data, /opt, PWD"
      return 1
    fi
    new_home="$base/terminal-home-$(id -un 2>/dev/null || echo user)"
    TB_HOME="$new_home"
    TB_FAKE_HOME=1
    if [ "$TB_DRY_RUN" -eq 1 ]; then
      # Dry-run must not mutate the caller's shell: HOME stays untouched.
      info "DRY-RUN: would create and use fake HOME=$new_home (current HOME left unchanged)"
      return 0
    fi
    secure_fake_home "$new_home" || return 1
    export HOME="$new_home"
    info "using fake HOME=$HOME"
  fi

  if [ "$TB_DRY_RUN" -eq 0 ]; then
    TB_LOG="$TB_HOME/terminal-bootstrap.log"
    # Rotate an oversized log so it never grows unbounded.
    if [ -f "$TB_LOG" ] && [ "$(file_size "$TB_LOG")" -gt "$TB_LOG_MAX_BYTES" ] 2>/dev/null; then
      mv "$TB_LOG" "$TB_LOG.1" 2>/dev/null && info "rotated log to $TB_LOG.1"
    fi
    touch "$TB_LOG" 2>/dev/null || { TB_LOG="$TB_INITIAL_LOG"; warn "cannot write HOME log; using $TB_LOG"; }
    if [ "$TB_LOG" != "$TB_INITIAL_LOG" ] && [ -f "$TB_INITIAL_LOG" ]; then
      cat "$TB_INITIAL_LOG" >> "$TB_LOG" 2>/dev/null
      rm -f "$TB_INITIAL_LOG" 2>/dev/null
    fi
    cd "$TB_HOME" 2>/dev/null || warn "cd HOME failed: $TB_HOME"
  fi
}

check_terminal() {
  local colors
  colors="$(tput colors 2>/dev/null)"
  [ -n "$colors" ] || colors=0
  info "tput colors=$colors"
  [ "$colors" = 8 ] && info "8-color terminal detected; using safe ANSI colors"
  [ "$colors" != 8 ] && [ "$colors" != 16 ] && [ "$colors" != 256 ] && warn "color support unclear; ANSI colors may render poorly"

  if [ -z "${TERM:-}" ] || [ "$TERM" = dumb ]; then
    if [ "$TB_DRY_RUN" -eq 1 ]; then
      info "DRY-RUN: would set TERM=xterm"
    else
      export TERM=xterm
      warn "TERM was empty/dumb; set TERM=xterm"
    fi
  fi
}

# A file is only modified when its markers are sane: equal start/end counts
# and at most one block. A missing end marker would otherwise truncate
# everything below the start marker.
validate_managed_markers() {
  local file="$1" start="$2" end="$3" starts ends
  [ -f "$file" ] || return 0
  starts="$(grep -Fxc -- "$start" "$file" 2>/dev/null)" || starts=0
  ends="$(grep -Fxc -- "$end" "$file" 2>/dev/null)" || ends=0
  [ "$starts" = "$ends" ] && [ "$starts" -le 1 ]
}

extract_managed_block() {
  local file="$1" start="$2" end="$3"
  [ -f "$file" ] || return 0
  awk -v s="$start" -v e="$end" '$0==s{f=1;next} $0==e{f=0;next} f{print}' "$file" 2>/dev/null
}

# Atomically rewrite $file without its managed block. Permissions are
# preserved (cp -p onto the temp file, then a truncating write, then one mv).
# Command substitution drops trailing newlines, which also prevents blank
# lines from accumulating across runs.
remove_managed_block() {
  local file="$1" start="$2" end="$3" tmp remaining
  [ -f "$file" ] || return 0
  remaining="$(awk -v s="$start" -v e="$end" '$0==s{skip=1;next} $0==e{skip=0;next} !skip{print}' "$file" 2>/dev/null)" || return 1
  tmp="$(mktemp "$file.tmp.XXXXXX" 2>/dev/null)" || tmp="$file.tmp.$$"
  cp -p "$file" "$tmp" 2>/dev/null
  if [ -n "$remaining" ]; then
    printf '%s\n' "$remaining" > "$tmp" || { rm -f "$tmp" 2>/dev/null; return 1; }
  else
    : > "$tmp" || { rm -f "$tmp" 2>/dev/null; return 1; }
  fi
  mv "$tmp" "$file" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
}

append_managed_block() {
  local file="$1" start="$2" end="$3" label="$4" new_block new_inner existing remaining tmp
  new_block="$(cat)"
  if [ "$TB_DRY_RUN" -eq 1 ]; then
    info "DRY-RUN: would preserve existing $file and append/replace managed block: $label"
    return 0
  fi
  if ! validate_managed_markers "$file" "$start" "$end"; then
    err "refusing to modify $file: unbalanced or duplicate managed markers ($label)"
    return 1
  fi
  # Skip the rewrite (and the backup) when the block is already up to date.
  new_inner="$(printf '%s\n' "$new_block" | awk -v s="$start" -v e="$end" '$0==s{f=1;next} $0==e{f=0;next} f{print}')"
  existing="$(extract_managed_block "$file" "$start" "$end")"
  if [ -n "$existing" ] && [ "$existing" = "$new_inner" ]; then
    info "managed block already up to date in $file: $label"
    return 0
  fi
  backup_file "$file" || { err "refusing to modify $file without a backup"; return 1; }
  remaining=''
  [ -f "$file" ] && remaining="$(awk -v s="$start" -v e="$end" '$0==s{skip=1;next} $0==e{skip=0;next} !skip{print}' "$file" 2>/dev/null)"
  tmp="$(mktemp "$file.tmp.XXXXXX" 2>/dev/null)" || tmp="$file.tmp.$$"
  [ -f "$file" ] && cp -p "$file" "$tmp" 2>/dev/null
  {
    [ -n "$remaining" ] && printf '%s\n\n' "$remaining"
    printf '%s\n' "$new_block"
  } > "$tmp" || { rm -f "$tmp" 2>/dev/null; err "cannot write $tmp"; return 1; }
  mv "$tmp" "$file" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; err "cannot update $file"; return 1; }
  info "updated $file with managed block: $label"
}

# Install a fully generated file from a prepared temp file, skipping
# the write (and backup) when nothing changed.
install_generated_file() {
  local tmp="$1" dest="$2" label="$3" mode="${4:-}"
  if [ -f "$dest" ] && cmp -s "$tmp" "$dest" 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null
    info "$label already up to date: $dest"
    return 0
  fi
  backup_file "$dest" || { rm -f "$tmp" 2>/dev/null; err "refusing to replace $dest without a backup"; return 1; }
  mv "$tmp" "$dest" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; err "cannot write $dest"; return 1; }
  [ -n "$mode" ] && chmod "$mode" "$dest" 2>/dev/null
  info "wrote $label: $dest"
}

write_theme() {
  local file="$TB_HOME/.terminal-bootstrap-theme.sh" tmp
  if [ "$TB_DRY_RUN" -eq 1 ]; then
    info "DRY-RUN: would write generated theme file $file"
    return 0
  fi
  tmp="$(mktemp "$file.tmp.XXXXXX" 2>/dev/null)" || tmp="$file.tmp.$$"
  {
    printf '# Terminal bootstrap theme v%s - 8-color safe\n' "$TB_VERSION"
    cat <<'THEME'
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
[ -z "$TERM" ] || [ "$TERM" = dumb ] && export TERM=xterm

# Local timezone for prompt and time helpers. Override before sourcing if needed.
export TERMINAL_BOOTSTRAP_TZ="${TERMINAL_BOOTSTRAP_TZ:-Australia/Melbourne}"

export HISTSIZE=20000 HISTFILESIZE=40000 HISTCONTROL=ignoreboth:erasedups HISTTIMEFORMAT="%F %T  "
shopt -s histappend checkwinsize cdspell dirspell extglob globstar 2>/dev/null
bind '"\e[A": history-search-backward' 2>/dev/null
bind '"\e[B": history-search-forward' 2>/dev/null
[ -f "$HOME/.inputrc" ] && bind -f "$HOME/.inputrc" 2>/dev/null

# Keep deep paths readable in the prompt's \w.
PROMPT_DIRTRIM="${TERMINAL_BOOTSTRAP_DIRTRIM:-3}"
# The prompt shows the venv name itself; stop venvs prepending their own.
export VIRTUAL_ENV_DISABLE_PROMPT=1

export LESS='-R -F -X' LESSHISTFILE=-
export LESS_TERMCAP_mb=$'\e[1;31m' LESS_TERMCAP_md=$'\e[1;36m' LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[1;44;33m' LESS_TERMCAP_se=$'\e[0m' LESS_TERMCAP_us=$'\e[1;32m' LESS_TERMCAP_ue=$'\e[0m'
export GREP_COLORS='mt=01;33:fn=35:ln=32:se=36'
command -v dircolors >/dev/null 2>&1 && eval "$(dircolors -b 2>/dev/null)"

__tb_ls_extra=''
ls --group-directories-first . >/dev/null 2>&1 && __tb_ls_extra=' --group-directories-first'
alias ls="ls --color=auto${__tb_ls_extra}"
alias ll="ls -alFh --color=auto${__tb_ls_extra}"
alias la="ls -Ah --color=auto${__tb_ls_extra}"
alias l="ls -CF --color=auto${__tb_ls_extra}"
alias grep='grep --color=auto'
alias egrep='egrep --color=auto'
alias fgrep='fgrep --color=auto'
diff --color=auto /dev/null /dev/null >/dev/null 2>&1 && alias diff='diff --color=auto'

alias c='clear'
alias cls='clear'
alias p='pwd'
alias h='history'
alias h50='history 50'
alias pathlist='echo "$PATH" | tr ":" "\n"'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias dfh='df -hT'
alias duh='du -h --max-depth=1 2>/dev/null | sort -h'
alias du1='du -h --max-depth=1 2>/dev/null | sort -h'
alias mem='free -h'
alias ports='ss -tulpn'
alias listen='ss -tulpn'
alias ip4='ip -4 -br addr'
alias ip6='ip -6 -br addr'
alias route4='ip route'
alias now='local_time'
alias today='local_date'
alias utcnow='TZ=UTC date "+%Y-%m-%d %H:%M:%S %Z"'
alias reload_bootstrap='source "$HOME/.terminal-bootstrap-theme.sh"'
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Does find support -printf (GNU)? Approximate fallbacks are used when not.
__tb_find_printf=0
find /dev/null -maxdepth 0 -printf '' >/dev/null 2>&1 && __tb_find_printf=1

mkcd(){ mkdir -p "$1" && cd "$1"; }
path(){ echo "$PATH" | tr ':' '\n'; }
pathgrep(){ [ -n "$1" ] || { echo 'usage: pathgrep <pattern>' >&2; return 2; }; echo "$PATH" | tr ':' '\n' | grep -i --color=auto -- "$@"; }
local_time(){ TZ="$TERMINAL_BOOTSTRAP_TZ" date '+%Y-%m-%d %H:%M:%S %Z'; }
local_date(){ TZ="$TERMINAL_BOOTSTRAP_TZ" date '+%Y-%m-%d'; }
timezone(){ echo "$TERMINAL_BOOTSTRAP_TZ"; }
set_timezone(){ export TERMINAL_BOOTSTRAP_TZ="$1"; echo "TERMINAL_BOOTSTRAP_TZ=$TERMINAL_BOOTSTRAP_TZ"; }
myip(){
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$ip" ] || ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<NF; i++) if ($i == "src") {print $(i+1); exit}}')"
  printf '%s\n' "${ip:-no-ip}"
}
lt(){ local depth="${1:-2}"; command -v tree >/dev/null 2>&1 && tree -C -a -L "$depth" || find . -maxdepth "$depth" -print | sed 's#^\./##' | sort; }
psg(){ [ -n "$1" ] || { echo 'usage: psg <pattern>' >&2; return 2; }; ps aux | grep -i --color=auto -- "$@" | grep -v grep; }
hgrep(){ [ -n "$1" ] || { echo 'usage: hgrep <pattern>' >&2; return 2; }; history | grep -i --color=auto -- "$@"; }
findname(){ [ -n "$1" ] || { echo 'usage: findname <name-fragment>' >&2; return 2; }; find . -iname "*$1*" 2>/dev/null; }
findtext(){ [ -n "$1" ] || { echo 'usage: findtext <pattern>' >&2; return 2; }; grep -RIn --color=auto --exclude-dir=.git -- "$1" . 2>/dev/null; }
tailf(){ tail -n "${2:-200}" -f "$1"; }
loggrep(){ [ -n "$1" ] || { echo 'usage: loggrep <pattern>' >&2; return 2; }; grep -RIn --color=auto -- "$1" ./*.log ./*/*.log 2>/dev/null; }
topcpu(){ ps -eo pid,ppid,user,%cpu,%mem,etime,cmd --sort=-%cpu 2>/dev/null | head -n "${1:-15}"; }
topmem(){ ps -eo pid,ppid,user,%cpu,%mem,etime,cmd --sort=-%mem 2>/dev/null | head -n "${1:-15}"; }
bigfiles(){
  if [ "$__tb_find_printf" = 1 ]; then
    find "${1:-.}" -type f -printf '%s %p\n' 2>/dev/null | sort -nr | head -n "${2:-20}" | awk '{size=$1; $1=""; printf "%.2f MB %s\n", size/1024/1024, $0}'
  else
    # Approximate fallback: per-file du in KB, files only.
    find "${1:-.}" -type f -exec du -k {} + 2>/dev/null | sort -nr | head -n "${2:-20}" | awk '{size=$1; $1=""; printf "%.2f MB %s\n", size/1024, $0}'
  fi
}
recent(){
  if [ "$__tb_find_printf" = 1 ]; then
    find "${1:-.}" -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort -r | head -n "${2:-20}"
  else
    # Approximate fallback: ls -t sorts per batch, not globally.
    find "${1:-.}" -type f -exec ls -dlt {} + 2>/dev/null | head -n "${2:-20}"
  fi
}
dux(){ du -h --max-depth="${2:-1}" "${1:-.}" 2>/dev/null | sort -hr | head -n "${3:-20}"; }
extract(){
  [ -f "$1" ] || { echo "usage: extract <archive-file>" >&2; return 1; }
  case "$1" in
    *.tar.bz2|*.tbz2) tar xjf "$1" ;;
    *.tar.gz|*.tgz) tar xzf "$1" ;;
    *.tar.xz|*.txz) tar xJf "$1" ;;
    *.tar) tar xf "$1" ;;
    *.gz) gunzip "$1" ;;
    *.bz2) bunzip2 "$1" ;;
    *.zip) unzip "$1" ;;
    *) echo "cannot extract: $1" >&2; return 1 ;;
  esac
}
json_pretty(){
  # Pick the interpreter by availability; a JSON error must surface, not
  # trigger a silent second attempt (which would also lose piped stdin).
  if command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool "$@"
  elif command -v python >/dev/null 2>&1; then
    python -m json.tool "$@"
  else
    echo 'json_pretty: no python interpreter found' >&2
    return 127
  fi
}
# Local-only by default; use serve_public to expose on all interfaces.
serve_here(){ python3 -m http.server "${1:-8000}" --bind 127.0.0.1; }
serve_public(){
  echo "serving $(pwd) on ALL interfaces (port ${1:-8000}) — anyone who can reach this host can read it" >&2
  python3 -m http.server "${1:-8000}"
}

# TCP reachability without nc/telnet, using bash's built-in /dev/tcp.
# Host and port are passed as positional parameters, never interpolated
# into shell code.
port_open(){
  local host="$1" port="$2" t="${3:-3}"
  [ -n "$host" ] && [ -n "$port" ] || { echo 'usage: port_open <host> <port> [timeout-seconds]' >&2; return 2; }
  case "$port" in ''|*[!0-9]*) echo "port_open: port must be numeric: $port" >&2; return 2 ;; esac
  case "$t" in ''|*[!0-9]*) echo "port_open: timeout must be numeric: $t" >&2; return 2 ;; esac
  case "$host" in *[![:alnum:].:_-]*|'') echo "port_open: invalid host: $host" >&2; return 2 ;; esac
  if command -v timeout >/dev/null 2>&1; then
    if timeout "$t" bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$host" "$port" 2>/dev/null; then
      echo "OPEN $host:$port"
    else
      echo "CLOSED/FILTERED $host:$port (within ${t}s)"; return 1
    fi
  else
    # Without timeout(1) a filtered port may hang until the TCP timeout.
    if bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$host" "$port" 2>/dev/null; then
      echo "OPEN $host:$port"
    else
      echo "CLOSED $host:$port"; return 1
    fi
  fi
}
httpcheck(){
  [ -n "$1" ] || { echo 'usage: httpcheck <url> [timeout-seconds]' >&2; return 2; }
  curl -sS -o /dev/null -m "${2:-10}" -w 'status=%{http_code} time=%{time_total}s size=%{size_download}B\n' "$1"
}
retry(){
  local n="$1" i=1 delay=2
  case "$n" in ''|*[!0-9]*) echo 'usage: retry <attempts> <command...>' >&2; return 2 ;; esac
  shift
  [ "$#" -gt 0 ] || { echo 'usage: retry <attempts> <command...>' >&2; return 2; }
  while true; do
    "$@" && return 0
    [ "$i" -ge "$n" ] && { echo "retry: failed after $n attempts: $*" >&2; return 1; }
    echo "retry: attempt $i failed; sleeping ${delay}s" >&2
    sleep "$delay"
    delay=$((delay * 2))
    i=$((i + 1))
  done
}
watchcmd(){
  local interval=2
  case "${1:-}" in ''|*[!0-9]*) ;; *) interval="$1"; shift ;; esac
  [ "$#" -gt 0 ] || { echo 'usage: watchcmd [interval-seconds] <command...>' >&2; return 2; }
  while true; do
    clear 2>/dev/null
    printf '%s  every %ss: %s\n\n' "$(local_time)" "$interval" "$*"
    "$@"
    sleep "$interval" || return
  done
}
csvview(){
  [ -f "$1" ] || { echo 'usage: csvview <file> [delimiter]' >&2; return 2; }
  if command -v column >/dev/null 2>&1; then
    column -t -s "${2:-,}" < "$1" | less -S
  else
    less -S "$1"
  fi
}
epoch2date(){
  local e="$1" utc_out local_out
  case "$e" in ''|*[!0-9]*) echo 'usage: epoch2date <epoch-seconds-or-millis>' >&2; return 2 ;; esac
  [ "${#e}" -gt 11 ] && e=$((e / 1000))   # millisecond epochs
  utc_out="$(TZ=UTC date -d "@$e" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null)" || { echo 'epoch2date: needs GNU date' >&2; return 1; }
  local_out="$(TZ="$TERMINAL_BOOTSTRAP_TZ" date -d "@$e" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null)"
  echo "UTC   : $utc_out"
  echo "Local : $local_out"
}
date2epoch(){
  [ -n "$*" ] || { echo 'usage: date2epoch <date-string>' >&2; return 2; }
  TZ="$TERMINAL_BOOTSTRAP_TZ" date -d "$*" +%s 2>/dev/null || { echo 'date2epoch: cannot parse (needs GNU date)' >&2; return 1; }
}

# --- XML helpers -------------------------------------------------------
# xmllint when available, python3 otherwise. Tag matching ignores XML
# namespaces (matches on the local name), because namespaced enterprise
# XML is where these helpers are needed most.

xmlview(){
  [ -f "$1" ] || { echo 'usage: xmlview <file.xml>' >&2; return 2; }
  if command -v xmllint >/dev/null 2>&1; then
    xmllint --format "$1" | less -S
  else
    # minidom loads the whole file; fine for viewing-sized XML
    python3 -c 'import sys, xml.dom.minidom as m; sys.stdout.write(m.parse(sys.argv[1]).toprettyxml(indent="  "))' "$1" 2>/dev/null \
      | grep -v '^[[:space:]]*$' | less -S
  fi
}

xmlcheck(){
  [ -f "$1" ] || { echo 'usage: xmlcheck <file.xml>' >&2; return 2; }
  if command -v xmllint >/dev/null 2>&1; then
    xmllint --noout "$1" && echo "OK: well-formed"
  else
    python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1]); print("OK: well-formed")' "$1"
  fi
}

# Print every <tag> element in full (namespace-insensitive). Streams, so
# large files are fine. Optional third arg caps the number of matches.
xmltag(){
  [ -f "$1" ] && [ -n "$2" ] || { echo 'usage: xmltag <file.xml> <tag> [max-matches]' >&2; return 2; }
  python3 - "$1" "$2" "${3:-0}" <<'PYTAG'
import sys, xml.etree.ElementTree as ET
path, tag, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
n = 0
for _, el in ET.iterparse(path):
    if el.tag.rsplit('}', 1)[-1] == tag:
        n += 1
        try:
            ET.indent(el, space='  ')   # python >= 3.9
        except AttributeError:
            pass
        print(ET.tostring(el, encoding='unicode').strip())
        print('---')
        if limit and n >= limit:
            break
print('%d match(es)' % n, file=sys.stderr)
sys.exit(0 if n else 1)
PYTAG
}

# Print only the text content of every <tag> (one per line) — pipeable.
xmlvalue(){
  [ -f "$1" ] && [ -n "$2" ] || { echo 'usage: xmlvalue <file.xml> <tag>' >&2; return 2; }
  python3 - "$1" "$2" <<'PYVAL'
import sys, xml.etree.ElementTree as ET
path, tag = sys.argv[1], sys.argv[2]
n = 0
for _, el in ET.iterparse(path):
    if el.tag.rsplit('}', 1)[-1] == tag:
        n += 1
        print(''.join(el.itertext()).strip())
sys.exit(0 if n else 1)
PYVAL
}

# Print an attribute's value from every <tag> that carries it.
xmlattr(){
  [ -f "$1" ] && [ -n "$2" ] && [ -n "$3" ] || { echo 'usage: xmlattr <file.xml> <tag> <attribute>' >&2; return 2; }
  python3 - "$1" "$2" "$3" <<'PYATTR'
import sys, xml.etree.ElementTree as ET
path, tag, attr = sys.argv[1], sys.argv[2], sys.argv[3]
def ln(t): return t.rsplit('}', 1)[-1]
n = 0
for _, el in ET.iterparse(path):
    if ln(el.tag) == tag:
        for k, v in el.attrib.items():
            if ln(k) == attr:
                n += 1
                print(v)
sys.exit(0 if n else 1)
PYATTR
}

xmlcount(){
  [ -f "$1" ] && [ -n "$2" ] || { echo 'usage: xmlcount <file.xml> <tag>' >&2; return 2; }
  python3 - "$1" "$2" <<'PYCNT'
import sys, xml.etree.ElementTree as ET
path, tag = sys.argv[1], sys.argv[2]
print(sum(1 for _, el in ET.iterparse(path) if el.tag.rsplit('}', 1)[-1] == tag))
PYCNT
}

# Search tag names, attributes, and text (case-insensitive regex) and
# print the path of each matching element, with its attributes and text.
xmlfind(){
  [ -f "$1" ] && [ -n "$2" ] || { echo 'usage: xmlfind <file.xml> <pattern>' >&2; return 2; }
  python3 - "$1" "$2" <<'PYFIND'
import re, sys, xml.etree.ElementTree as ET
path, pat = sys.argv[1], sys.argv[2]
rx = re.compile(pat, re.I)
def ln(t): return t.rsplit('}', 1)[-1]
stack, n = [], 0
for ev, el in ET.iterparse(path, events=('start', 'end')):
    if ev == 'start':
        stack.append(ln(el.tag))
        continue
    text = (el.text or '').strip()
    hit = rx.search(ln(el.tag)) or rx.search(text)
    if not hit:
        for k, v in el.attrib.items():
            if rx.search(ln(k)) or rx.search(str(v)):
                hit = True
                break
    if hit:
        n += 1
        loc = '/' + '/'.join(stack)
        attrs = ' '.join('%s="%s"' % (ln(k), v) for k, v in el.attrib.items())
        line = loc
        if attrs:
            line += ' [' + attrs + ']'
        if text:
            line += ' = ' + (text[:100] + ('...' if len(text) > 100 else ''))
        print(line)
    stack.pop()
print('%d match(es)' % n, file=sys.stderr)
sys.exit(0 if n else 1)
PYFIND
}

# Raw XPath for full control (needs xmllint). Quote the expression.
xmlxpath(){
  [ -f "$1" ] && [ -n "$2" ] || { echo "usage: xmlxpath <file.xml> '<xpath>'   e.g. xmlxpath f.xml '//order/@id'" >&2; return 2; }
  command -v xmllint >/dev/null 2>&1 || { echo 'xmlxpath: needs xmllint (use xmltag/xmlvalue/xmlfind instead)' >&2; return 127; }
  xmllint --xpath "$2" "$1" && echo
}

instance_info(){
  echo "User      : $(whoami)"
  echo "Host      : $(hostname)"
  echo "Private IP: $(myip)"
  echo "Kernel    : $(uname -r)"
  echo "Uptime    : $(uptime -p 2>/dev/null || uptime)"
  echo "Local TZ  : ${TERMINAL_BOOTSTRAP_TZ}"
  echo "Local Date: $(TZ="$TERMINAL_BOOTSTRAP_TZ" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "UTC Date  : $(TZ=UTC date '+%Y-%m-%d %H:%M:%S %Z')"
  if [ -f /.dockerenv ] || grep -qsE 'docker|containerd|kubepods' /proc/1/cgroup 2>/dev/null; then
    echo "Container : yes"
  fi
  if command -v curl >/dev/null 2>&1; then
    local token instance_id az itype region
    token=$(curl -fsS -m 1 -X PUT -H "X-aws-ec2-metadata-token-ttl-seconds: 60" http://169.254.169.254/latest/api/token 2>/dev/null)
    if [ -n "$token" ]; then
      instance_id=$(curl -fsS -m 1 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
      itype=$(curl -fsS -m 1 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null)
      az=$(curl -fsS -m 1 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/placement/availability-zone 2>/dev/null)
      region=$(curl -fsS -m 1 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null)
      [ -n "$instance_id" ] && echo "EC2 ID    : $instance_id"
      [ -n "$itype" ] && echo "EC2 Type  : $itype"
      [ -n "$az" ] && echo "AZ        : $az"
      [ -n "$region" ] && echo "Region    : $region"
    fi
  fi
}
alias instance-info='instance_info' 2>/dev/null || true

C_RESET='\[\e[0m\]'
C_BOLD='\[\e[1m\]'
C_BLACK='\[\e[30m\]'
C_GREEN='\[\e[32m\]'
C_YELLOW='\[\e[33m\]'
C_BLUE='\[\e[34m\]'
C_MAGENTA='\[\e[35m\]'
C_CYAN='\[\e[36m\]'
C_WHITE='\[\e[37m\]'
C_BG_RED='\[\e[41m\]'
C_BG_GREEN='\[\e[42m\]'
TERMINAL_BOOTSTRAP_IP="$(myip)"
[ -z "$TERMINAL_BOOTSTRAP_IP" ] && TERMINAL_BOOTSTRAP_IP=no-ip
__tb_ip_checked=$SECONDS

__terminal_bootstrap_git_branch(){
  command -v git >/dev/null 2>&1 || return
  local branch dirty
  branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null) || return
  dirty=''
  [ "${TERMINAL_BOOTSTRAP_GIT_DIRTY:-0}" = 1 ] && { git diff --quiet --ignore-submodules -- 2>/dev/null || dirty='*'; }
  printf 'git:%s%s' "$branch" "$dirty"
}

# Slow-command timer. The DEBUG trap stamps the start of the first command
# after the prompt chain has fully finished: __terminal_bootstrap_arm runs as
# the LAST element of PROMPT_COMMAND, so DEBUG firings for other prompt hooks
# never arm the timer (they would otherwise count idle time at the prompt).
# Skipped if another DEBUG trap is already installed.
__tb_ready=0
__terminal_bootstrap_arm(){ __tb_ready=1; }
if [ "${TERMINAL_BOOTSTRAP_TIMER:-1}" = 1 ] && [ -z "$(trap -p DEBUG)" ]; then
  trap '[ "${__tb_ready:-0}" = 1 ] && { __tb_ready=0; __tb_cmd_start=$SECONDS; }' DEBUG
fi

__terminal_bootstrap_prompt(){
  local exit_code=$? status git_text prompt_time top bottom dur dur_text='' jobs_n jobs_text='' venv_text=''
  history -a 2>/dev/null   # persist history now; gateway sessions die unclean

  if [ -n "${__tb_cmd_start:-}" ]; then
    dur=$((SECONDS - __tb_cmd_start))
    unset __tb_cmd_start
    if [ "$dur" -ge "${TERMINAL_BOOTSTRAP_SLOW_SECS:-5}" ]; then
      if [ "$dur" -ge 60 ]; then
        dur_text=" ${C_YELLOW}took $((dur / 60))m$((dur % 60))s${C_RESET}"
      else
        dur_text=" ${C_YELLOW}took ${dur}s${C_RESET}"
      fi
    fi
  fi

  # Refresh the cached IP occasionally (VPN/DHCP changes).
  if [ $((SECONDS - ${__tb_ip_checked:-0})) -ge "${TERMINAL_BOOTSTRAP_IP_TTL:-60}" ]; then
    TERMINAL_BOOTSTRAP_IP="$(myip)"
    [ -z "$TERMINAL_BOOTSTRAP_IP" ] && TERMINAL_BOOTSTRAP_IP=no-ip
    __tb_ip_checked=$SECONDS
  fi

  jobs_n=$(jobs -p 2>/dev/null | wc -l | tr -d ' ')
  [ "${jobs_n:-0}" -gt 0 ] && jobs_text=" ${C_MAGENTA}jobs:${jobs_n}${C_RESET}"

  if [ -n "${VIRTUAL_ENV:-}" ]; then
    venv_text="${C_CYAN}(${VIRTUAL_ENV##*/})${C_RESET} "
  elif [ -n "${CONDA_DEFAULT_ENV:-}" ] && [ "${CONDA_DEFAULT_ENV}" != base ]; then
    venv_text="${C_CYAN}(${CONDA_DEFAULT_ENV})${C_RESET} "
  fi

  prompt_time="$(TZ="$TERMINAL_BOOTSTRAP_TZ" date '+%H:%M')"
  [ "$exit_code" -eq 0 ] && status="${C_BG_GREEN}${C_BLACK} OK ${C_RESET}" || status="${C_BG_RED}${C_WHITE} ERR:${exit_code} ${C_RESET}"
  git_text="$(__terminal_bootstrap_git_branch)"
  [ -n "$git_text" ] && git_text=" ${C_MAGENTA}${git_text}${C_RESET}"

  if [ "${TERMINAL_BOOTSTRAP_PROMPT_LAYOUT:-single}" = multiline ]; then
    if [ "${TERMINAL_BOOTSTRAP_PROMPT_STYLE:-unicode}" = ascii ]; then top='+--'; bottom='+--'; else top='┌─'; bottom='└─'; fi
    PS1="${C_BLUE}${top}${C_RESET} ${venv_text}${C_BOLD}${C_GREEN}\u@\h${C_RESET} ${C_YELLOW}${TERMINAL_BOOTSTRAP_IP}${C_RESET} ${C_CYAN}${prompt_time}${C_RESET} ${status}${dur_text}${git_text}${jobs_text}
${C_BLUE}${bottom}${C_RESET} ${C_BOLD}${C_CYAN}\w${C_RESET}
${C_GREEN}\\$ ${C_RESET}"
  else
    PS1="${venv_text}${C_BOLD}${C_GREEN}\u@\h${C_RESET} ${C_YELLOW}${TERMINAL_BOOTSTRAP_IP}${C_RESET} ${C_CYAN}${prompt_time}${C_RESET} ${status}${dur_text}${git_text}${jobs_text} ${C_BOLD}${C_CYAN}\w${C_RESET} ${C_GREEN}\\$ ${C_RESET}"
  fi
}

# Install the prompt hook first (to capture the exit code) and the timer
# arm hook last (so other prompt hooks never arm the timer). Handles both
# scalar PROMPT_COMMAND and the bash >= 5.1 array form without flattening.
case "$(declare -p PROMPT_COMMAND 2>/dev/null)" in
  "declare -a"*)
    __tb_found=0
    for __tb_entry in "${PROMPT_COMMAND[@]}"; do
      [ "$__tb_entry" = __terminal_bootstrap_prompt ] && __tb_found=1
    done
    if [ "$__tb_found" -eq 0 ]; then
      PROMPT_COMMAND=(__terminal_bootstrap_prompt "${PROMPT_COMMAND[@]}" __terminal_bootstrap_arm)
    fi
    unset __tb_found __tb_entry
    ;;
  *)
    case ";${PROMPT_COMMAND:-};" in
      *";__terminal_bootstrap_prompt;"*) ;;
      *) PROMPT_COMMAND="__terminal_bootstrap_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND};__terminal_bootstrap_arm" ;;
    esac
    ;;
esac
THEME
  } > "$tmp"
  if ! bash -n "$tmp" 2>>"$TB_LOG"; then
    rm -f "$tmp" 2>/dev/null
    err "theme syntax check failed; not installed: $file"
    return 1
  fi
  install_generated_file "$tmp" "$file" "theme"
}

update_bashrc() {
  local file="$TB_HOME/.bashrc" start='# >>> TERMINAL_BOOTSTRAP >>>' end='# <<< TERMINAL_BOOTSTRAP <<<'
  append_managed_block "$file" "$start" "$end" "bash theme loader" <<RC
# >>> TERMINAL_BOOTSTRAP >>>
# terminal-bootstrap v$TB_VERSION
[ -f "\$HOME/.terminal-bootstrap-theme.sh" ] && . "\$HOME/.terminal-bootstrap-theme.sh"
# <<< TERMINAL_BOOTSTRAP <<<
RC
}

write_inputrc() {
  local file="$TB_HOME/.inputrc" start='# >>> TERMINAL_BOOTSTRAP >>>' end='# <<< TERMINAL_BOOTSTRAP <<<'
  append_managed_block "$file" "$start" "$end" "readline settings" <<INP
# >>> TERMINAL_BOOTSTRAP >>>
# terminal-bootstrap v$TB_VERSION
set completion-ignore-case On
set show-all-if-ambiguous On
set show-all-if-unmodified On
set colored-stats On
set colored-completion-prefix On
"\e[A": history-search-backward
"\e[B": history-search-forward
# <<< TERMINAL_BOOTSTRAP <<<
INP
}

write_activate() {
  local file="$TB_HOME/activate-terminal-bootstrap.sh" tmp
  if [ "$TB_DRY_RUN" -eq 1 ]; then
    info "DRY-RUN: would write activation script $file"
    return 0
  fi
  tmp="$(mktemp "$file.tmp.XXXXXX" 2>/dev/null)" || tmp="$file.tmp.$$"
  {
    printf '# terminal-bootstrap v%s\n' "$TB_VERSION"
    printf '# Usage: source "%s"\n' "$file"
    # %q renders each value as a safely quoted shell word.
    printf 'export HOME=%q\n' "$TB_HOME"
    printf 'export TERMINAL_BOOTSTRAP_TZ=%q\n' "${TERMINAL_BOOTSTRAP_TZ:-Australia/Melbourne}"
    printf 'export TERMINAL_BOOTSTRAP_PROMPT_LAYOUT=%q\n' "${TERMINAL_BOOTSTRAP_PROMPT_LAYOUT:-single}"
    cat <<'ACTIVATE'
[ -z "$TERM" ] || [ "$TERM" = dumb ] && export TERM=xterm
[ -f "$HOME/.inputrc" ] && bind -f "$HOME/.inputrc" 2>/dev/null
[ -f "$HOME/.terminal-bootstrap-theme.sh" ] && . "$HOME/.terminal-bootstrap-theme.sh"
cd "$HOME" 2>/dev/null || true
ACTIVATE
  } > "$tmp"
  if ! bash -n "$tmp" 2>>"$TB_LOG"; then
    rm -f "$tmp" 2>/dev/null
    warn "activation script syntax check failed; not installed: $file"
    return 1
  fi
  install_generated_file "$tmp" "$file" "activation script" 700
}

uninstall() {
  local rc_start='# >>> TERMINAL_BOOTSTRAP >>>' rc_end='# <<< TERMINAL_BOOTSTRAP <<<'
  local f name

  if ! writable_dir "${TB_HOME:-}"; then
    warn "HOME missing or not writable: ${TB_HOME:-<empty>}; nothing to uninstall here"
    echo "If the setup used a fake HOME, source its activation script first, then rerun --uninstall."
    return 0
  fi

  if [ "$TB_DRY_RUN" -eq 0 ] && touch "$TB_HOME/terminal-bootstrap.log" 2>/dev/null; then
    TB_LOG="$TB_HOME/terminal-bootstrap.log"
    if [ -f "$TB_INITIAL_LOG" ]; then
      cat "$TB_INITIAL_LOG" >> "$TB_LOG" 2>/dev/null
      rm -f "$TB_INITIAL_LOG" 2>/dev/null
    fi
  fi

  for name in .bashrc .inputrc; do
    f="$TB_HOME/$name"
    [ -f "$f" ] || continue
    if ! validate_managed_markers "$f" "$rc_start" "$rc_end"; then
      err "refusing to touch $f: unbalanced or duplicate managed markers"
      continue
    fi
    if [ -z "$(extract_managed_block "$f" "$rc_start" "$rc_end")" ]; then
      info "no managed block in $f"
      continue
    fi
    if [ "$TB_DRY_RUN" -eq 1 ]; then
      info "DRY-RUN: would remove managed block from $f"
      continue
    fi
    backup_file "$f" || { err "refusing to modify $f without a backup"; continue; }
    if remove_managed_block "$f" "$rc_start" "$rc_end"; then
      info "removed managed block from $f"
    else
      err "failed to remove managed block from $f"
    fi
  done

  for name in .terminal-bootstrap-theme.sh activate-terminal-bootstrap.sh; do
    f="$TB_HOME/$name"
    [ -f "$f" ] || continue
    if [ "$TB_DRY_RUN" -eq 1 ]; then
      info "DRY-RUN: would remove $f"
    elif rm -f "$f" 2>/dev/null; then
      info "removed $f"
    else
      err "failed to remove $f"
    fi
  done

  if [ "$TB_ERRORS" -gt 0 ]; then
    echo "Uninstall INCOMPLETE: $TB_ERRORS error(s). See log: $TB_LOG"
  elif [ "$TB_WARNINGS" -gt 0 ]; then
    echo "Uninstalled terminal bootstrap v$TB_VERSION from $TB_HOME with $TB_WARNINGS warning(s). See log: $TB_LOG"
  else
    echo "Uninstalled terminal bootstrap v$TB_VERSION from $TB_HOME."
    echo "Backups (*.backup.*) and the log ($TB_LOG) were kept."
  fi
  echo "The current shell keeps its prompt/aliases until you start a new one."
}

summary() {
  echo
  echo '============================================================'
  echo 'Terminal bootstrap summary (minified)'
  echo '============================================================'
  echo "Version         : $TB_VERSION"
  echo "Dry run         : $TB_DRY_RUN"
  echo "HOME used       : $TB_HOME"
  if [ "$TB_DRY_RUN" -eq 1 ] && [ "$TB_FAKE_HOME" -eq 1 ]; then
    echo "  (dry run: current HOME left unchanged: ${TB_ORIGINAL_HOME:-<empty>})"
  fi
  echo "Fake HOME       : $TB_FAKE_HOME"
  echo "Timezone        : ${TERMINAL_BOOTSTRAP_TZ:-Australia/Melbourne}"
  echo "Prompt layout   : ${TERMINAL_BOOTSTRAP_PROMPT_LAYOUT:-single}"
  echo "Log file        : $TB_LOG"
  echo "Theme file      : $TB_HOME/.terminal-bootstrap-theme.sh"
  echo "Bash rc         : $TB_HOME/.bashrc"
  echo "Input rc        : $TB_HOME/.inputrc"
  echo "Activate script : $TB_HOME/activate-terminal-bootstrap.sh"
  echo "Warnings        : $TB_WARNINGS"
  echo "Errors          : $TB_ERRORS"
  echo
  if [ "$TB_DRY_RUN" -eq 1 ]; then
    echo 'Dry run only: no config files were changed.'
    echo
  fi
  if [ "$TB_FAKE_HOME" -eq 1 ] || ! is_sourced; then
    echo 'To activate in the current/future session, run:'
    echo "  source \"$TB_HOME/activate-terminal-bootstrap.sh\""
    echo
  fi
  echo 'Useful checks: echo $HOME ; timezone ; now ; instance_info ; mem ; ip4 ; topcpu ; topmem ; ll'
  echo 'New helpers  : port_open ; httpcheck ; retry ; watchcmd ; csvview ; epoch2date ; date2epoch ; dux'
  echo 'XML helpers  : xmlview ; xmlcheck ; xmltag ; xmlvalue ; xmlattr ; xmlcount ; xmlfind ; xmlxpath'
  echo '============================================================'
}

main() {
  if [ "$TB_UNINSTALL" -eq 1 ]; then
    info "starting terminal bootstrap uninstall (v$TB_VERSION)"
    uninstall
    if [ "$TB_ERRORS" -gt 0 ]; then finish 1; else finish 0; fi
    return $?
  fi
  info "starting terminal bootstrap v$TB_VERSION"
  export TERMINAL_BOOTSTRAP_TZ="${TERMINAL_BOOTSTRAP_TZ:-Australia/Melbourne}"
  export TERMINAL_BOOTSTRAP_PROMPT_LAYOUT="${TERMINAL_BOOTSTRAP_PROMPT_LAYOUT:-single}"
  for cmd in bash id getent tput awk sed hostname curl git ps free ss ip find grep tail tar unzip column timeout xmllint python3 python; do cmd_check "$cmd"; done
  setup_home || { summary; finish 1; return $?; }
  check_terminal
  write_theme
  update_bashrc
  write_inputrc
  write_activate
  if [ "$TB_DRY_RUN" -eq 0 ] && is_sourced; then
    . "$TB_HOME/.terminal-bootstrap-theme.sh"
    bind -f "$TB_HOME/.inputrc" 2>/dev/null
    info 'applied customization to current shell'
  fi
  if [ "$TB_DRY_RUN" -eq 0 ] && ! is_sourced; then
    warn 'executed, not sourced; current shell cannot inherit HOME/PS1 automatically'
  fi
  summary
  if [ "$TB_ERRORS" -gt 0 ]; then finish 1; else finish 0; fi
}

main "$@"
