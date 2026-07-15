# tmux — Terminal Multiplexer

## What it is

tmux is a **terminal multiplexer**: one terminal window can hold many shell
sessions at once, and those sessions keep running even when you disconnect.

Think of it as a window manager that lives inside your terminal:

- A **session** is a workspace — a named collection of windows that survives
  after you close your terminal or lose your SSH connection.
- A **window** is like a tab — each has its own shell, and a session can hold
  many of them.
- A **pane** is a split within a window — several shells visible side by side.

The killer feature is the **detach/reattach** model. Your programs run inside
the tmux *server*, not inside your terminal. Close the laptop, drop the VPN,
get kicked off SSH — the server keeps everything running, and you pick up
exactly where you left off with `tmux attach`.

## How to use

### Starting out

```sh
tmux                        # start a new unnamed session
tmux new -s work            # start a new session named "work"
tmux ls                     # list running sessions
tmux attach                 # reattach to the most recent session
tmux attach -t work         # reattach to a session by name
tmux kill-session -t work   # end a session and everything in it
```

### The prefix key

Every tmux keyboard command starts with a **prefix**: `Ctrl+b` by default.
Press and release the prefix, *then* press the command key. So "split the
window" is: hold `Ctrl`, press `b`, release both, press `%`.

Written shorthand throughout this guide: `prefix %` means `Ctrl+b` then `%`.

### A typical workflow

```sh
# on the server
tmux new -s etl             # 1. create a workspace for the task
# ... start a long-running job in one pane,
#     tail its log in another (prefix % to split) ...
# prefix d                  # 2. detach — the job keeps running
exit                        # 3. log out, go home

# later, from anywhere
ssh the-server
tmux attach -t etl          # 4. everything is still there, still running
```

### Configuration

tmux reads `~/.tmux.conf` at server start. A minimal, widely useful config:

```tmux
set -g mouse on              # click to select panes, scroll to scroll
set -g history-limit 50000   # keep plenty of scrollback
set -g base-index 1          # number windows from 1 (0 is far from the keys)
set -g status-interval 5     # refresh the status bar more often
```

Reload it into a running server with `tmux source-file ~/.tmux.conf`
(or `prefix :` then `source-file ~/.tmux.conf`).

> This repo's `scripts/terminal-bootstrap.sh` installs a managed,
> 8-color-safe `.tmux.conf` block (mouse on, 50k scrollback, styled status
> bar) suitable for restricted HTML5-gateway terminals. The minified
> `terminal-bootstrap-min.sh` variant deliberately leaves tmux alone.

## Benefits

- **Survives disconnects.** SSH drops, flaky VPNs, closed laptops — running
  jobs are unaffected. This alone makes tmux essential for remote work.
- **Long-running jobs without babysitting.** Kick off a migration or a data
  load, detach, and check on it tomorrow. No more `nohup ... &` and hunting
  for the output file.
- **One connection, many shells.** On a bastion host or gateway where each
  login is painful, a single SSH session gives you unlimited windows/panes.
- **Persistent context per project.** A named session holds your editor, your
  logs, and your shells arranged the way you left them — for weeks.
- **Side-by-side work.** Tail a log next to the process producing it; run a
  client next to a server; watch a dashboard while you type.
- **Pairing.** Two people attached to the same session see (and type into)
  the same screen — a zero-setup screen share over SSH.
- **Scriptable.** Sessions, windows, and panes can be created from shell
  scripts (`tmux new-session ... \; split-window ...`), so a whole project
  layout can be one command.

## Tips

- **Name your sessions** (`tmux new -s api-debug`). `tmux ls` output full of
  `0: 1 windows...` helps nobody.
- **Turn the mouse on** (`set -g mouse on`). Clicking panes and scrolling
  with the wheel removes most of the learning curve.
- **Rename windows as you go** (`prefix ,`). A status bar reading
  `logs | psql | editor` beats `bash | bash | bash`.
- **Use `tmux attach -d`** if the layout looks squashed — it detaches other
  (smaller) clients that are forcing the screen size down.
- **Zoom instead of un-splitting.** `prefix z` makes the current pane
  full-screen; press it again to restore the split.
- **Scrollback lives in copy mode.** Output scrolled past? `prefix [` then
  PgUp/arrows (or just wheel-scroll with mouse mode on). `q` to leave.
- **Big history buffer.** The default scrollback is small; set
  `history-limit` *before* windows are created — it isn't retroactive.
- **`exit` vs detach.** Typing `exit` in the last pane of the last window
  kills the session. To leave things running, detach (`prefix d`).
- **Nested tmux (tmux inside SSH inside tmux)**: press the prefix twice —
  `Ctrl+b Ctrl+b d` sends the detach to the *inner* tmux.
- **Don't run tmux inside tmux by accident.** If your prompt gains a second
  green bar, you probably attached from within a session.
- **Synchronize panes for fleet work.** `prefix :` then
  `setw synchronize-panes on` types into every pane at once — handy for
  a handful of servers, dangerous if you forget it's on.

## Shortcuts

All of these are `prefix` (`Ctrl+b`) followed by the key shown.

### Sessions

| Keys | Action |
|---|---|
| `d` | Detach — leave everything running |
| `s` | Pick a session from a list |
| `$` | Rename the current session |
| `(` / `)` | Previous / next session |

### Windows (tabs)

| Keys | Action |
|---|---|
| `c` | Create a new window |
| `,` | Rename the current window |
| `n` / `p` | Next / previous window |
| `0`–`9` | Jump to window by number |
| `w` | Pick a window from a list |
| `&` | Kill the current window (confirms first) |

### Panes (splits)

| Keys | Action |
|---|---|
| `%` | Split left/right |
| `"` | Split top/bottom |
| `←` `→` `↑` `↓` | Move between panes |
| `o` | Cycle to the next pane |
| `z` | Zoom pane to full screen (toggle) |
| `x` | Kill the current pane (confirms first) |
| `{` / `}` | Swap pane with the previous / next one |
| `Space` | Cycle through preset layouts |
| `q` | Show pane numbers (press a number to jump) |
| `!` | Break the pane out into its own window |

### Copy mode & misc

| Keys | Action |
|---|---|
| `[` | Enter copy mode (scroll with arrows / PgUp) |
| `]` | Paste the tmux buffer |
| `:` | Command prompt (type any tmux command) |
| `t` | Big clock (surprisingly useful for screenshares) |
| `?` | List every key binding |

In copy mode: `Space` starts a selection, `Enter` copies it, `q` quits.
(`Ctrl+Space` / `Ctrl+w` on emacs-style keys; `v` / `y` if you enable
`mode-keys vi`.)

## How to save your work

### Detach, don't exit — the built-in save

The everyday "save" is simply detaching (`prefix d`). The session — running
processes, window layout, scrollback — lives on inside the tmux server until
the *machine* reboots or you kill the session. `tmux attach -t name` is the
matching "load".

### Saving text out of a session

- **Quick copy**: enter copy mode (`prefix [`), select with `Space`, copy
  with `Enter`, paste into any pane with `prefix ]`.
- **Dump a pane's scrollback to a file**:

  ```sh
  tmux capture-pane -t etl -pS -50000 > pane-log.txt
  ```

  `-S -50000` reaches back that many lines into history; `-p` prints to
  stdout so you can redirect it.
- **Log a pane continuously**: `prefix :` then `pipe-pane -o 'cat >> ~/pane.log'`
  appends everything that appears in the pane to a file (run it again to
  stop). Start it *before* the interesting output happens.

### Surviving a reboot

A plain tmux session does **not** survive a server reboot — the tmux server
is just a process. Two plugins fix that:

- **[tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect)** —
  `prefix Ctrl+s` saves every session/window/pane (and optionally running
  programs); `prefix Ctrl+r` restores them after a reboot.
- **[tmux-continuum](https://github.com/tmux-plugins/tmux-continuum)** —
  builds on resurrect: auto-saves every 15 minutes and can auto-restore when
  tmux starts, so persistence becomes something you never think about.

Both install in one line each via [tpm](https://github.com/tmux-plugins/tpm),
the tmux plugin manager.

### Saving the layout as code

For layouts you rebuild often, script them instead of preserving them:

```sh
#!/usr/bin/env bash
tmux new-session -d -s etl -n job
tmux split-window -h -t etl:job          # log tail beside the job
tmux send-keys  -t etl:job.0 'cd ~/etl' Enter
tmux send-keys  -t etl:job.1 'tail -f ~/etl/run.log' Enter
tmux attach -t etl
```

Run the script and the workspace exists; no state to back up, nothing to
lose. Tools like [tmuxinator](https://github.com/tmuxinator/tmuxinator) do
the same thing declaratively from YAML if you prefer config over script.
