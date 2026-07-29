# GNU Nano Editor — Shortcuts & Reference

A practical reference for the GNU nano text editor on Linux: keyboard shortcuts,
command-line options, and configuration tips.

> **Notation:** `^X` means **Ctrl+X**. `M-X` means **Meta+X** — that's **Alt+X**
> on most keyboards (or press `Esc` then the key if Alt doesn't work, e.g. over
> some SSH/terminal setups). Shortcuts are case-insensitive for Ctrl combos.

The two lines at the bottom of nano's screen always show the most common
shortcuts for the current context — and `^G` opens full built-in help.

---

## 1. The essentials (survival kit)

| Shortcut | Action |
|---|---|
| `^G` | Open help |
| `^X` | Exit (prompts to save if modified) |
| `^O` | Write out (save) — Enter confirms the filename |
| `^S` | Save without prompting (newer nano versions) |
| `^W` | Search (Where-is) |
| `^\` | Search and replace |
| `^K` | Cut current line (or marked region) |
| `^U` | Paste (uncut) |
| `^C` | Show cursor position (line/column/char) |
| `M-U` | Undo |
| `M-E` | Redo |

To save under a different name: `^O`, edit the filename at the prompt, Enter.

---

## 2. Opening files from the command line

```sh
nano file.txt              # open (creates on save if missing)
nano +25 file.txt          # open at line 25
nano +25,10 file.txt       # open at line 25, column 10
nano -v file.txt           # view mode (read-only)
nano -B file.txt           # keep a backup (file~) on save
nano -l file.txt           # show line numbers
nano -m file.txt           # enable mouse support
nano -i file.txt           # auto-indent new lines
nano -E file.txt           # convert typed tabs to spaces
nano -T 4 file.txt         # tab width of 4 columns
nano -S file.txt           # soft-wrap long lines for display
nano -w file.txt           # never hard-wrap long lines (good for configs!)
nano -c file.txt           # constantly show cursor position
nano -R file.txt           # restricted mode (no file ops outside target)
nano file1 file2 file3     # open multiple buffers (M-< / M-> to switch)
```

> **Tip:** when editing config files, `nano -w` (no wrapping) prevents nano from
> silently inserting line breaks into long lines — historically a classic way to
> break config files (modern nano no longer hard-wraps by default, but `-w` makes
> it explicit).

---

## 3. Movement

| Shortcut | Action |
|---|---|
| `^F` / `^B` | Forward / back one character (or arrow keys) |
| `^P` / `^N` | Previous / next line |
| `^A` / `^E` | Start / end of line (Home / End) |
| `^Y` / `^V` | Page up / page down (PgUp / PgDn) |
| `M-\` (or `^Home`) | First line of file |
| `M-/` (or `^End`) | Last line of file |
| `^→` (Ctrl+Right) or `^Space` | Forward one word |
| `^←` (Ctrl+Left) or `M-Space` | Back one word |
| `^_` or `M-G` | **Go to line** (and optionally column: `25,10`) |
| `M-(` / `M-)` (or `M-9` / `M-0`) | Previous / next paragraph |
| `M-]` | Jump to matching bracket `(){}[]` |
| `M--` / `M-+` | Scroll view up / down one line without moving cursor |
| `M-A` then movement | See "Select" below — mark text while moving |
| `^L` | Refresh / center the screen on the cursor |

---

## 4. Editing

| Shortcut | Action |
|---|---|
| `^K` | Cut line (repeat to cut consecutive lines into one buffer) |
| `M-6` (or `M-^`) | Copy line (or marked region) instead of cutting |
| `^U` | Paste |
| `^D` | Delete character under cursor |
| `Backspace` / `^H` | Delete character before cursor |
| `M-Del` | Delete (zap) the current line entirely, without touching the cut buffer |
| `M-Backspace` | Delete backward from cursor to start of word |
| `^Del` | Delete forward from cursor to next word start |
| `M-U` | **Undo** |
| `M-E` | **Redo** |
| `^J` | Justify (re-wrap) the current paragraph |
| `M-J` | Justify the entire file |
| `^T` | Execute a function/command (older nano: spell check directly) |
| `F12` | Spell check, if available |
| `M-B` | Invoke the **linter**, if configured (NOT back-a-word — that's Ctrl+Left!) |
| `M-F` | Invoke the formatter, if configured |
| `M-3` (or `M-#`) | Comment / uncomment current line or marked region |
| `Tab` / `Shift-Tab` on a marked region | Indent / unindent the region |
| `^]` | Complete the word being typed (from words in the buffer) |
| `M-V` | Insert next keystroke verbatim (e.g. a literal Tab or control char) |
| `^I` | Insert a Tab |
| `M-Enter` (older `^M`) | Insert newline — Enter also auto-indents with `-i` |

---

## 5. Selecting (marking) text

1. Move to the start of the text.
2. Press `M-A` (or `^6`, or `^Shift-6`) to **set the mark**.
3. Move the cursor — text highlights as you go. (Shift+arrows also work in modern nano.)
4. Then:
   - `^K` — cut selection
   - `M-6` — copy selection
   - `^U` — paste wherever you like
   - `Tab` / `Shift-Tab` — indent / unindent selection
   - `M-3` — comment / uncomment selection
5. `M-A` again cancels the mark.

Select entire file: `M-\` (top), `M-A`, `M-/` (bottom). Cut all: follow with `^K`.

---

## 6. Search & replace

| Shortcut | Action |
|---|---|
| `^W` | Search forward |
| `^W` then `Enter` | Repeat last search |
| `M-W` (or `^W ^W`) | Repeat search, same direction |
| `M-Q` / `W` variants | Search backward (`^W` then `M-B` toggles direction) |
| `^\` (or `M-R`) | Search **and replace** |
| `^W` then `^R` | Switch from search to replace at the prompt |
| `^W` then `^T` | Switch from search to "go to line" |

At the search prompt these toggles are available:

| Toggle | Meaning |
|---|---|
| `M-C` | Case sensitivity on/off |
| `M-R` | Regular expressions on/off (ERE syntax) |
| `M-B` | Search backwards on/off |
| `^P` / `^N` | Recall earlier search terms (history) |

During a replace, answer per match: `Y` (yes), `N` (no), `A` (replace **all**),
`^C` (cancel).

**Regex replace example:** `^\`, toggle `M-R`, pattern `foo([0-9]+)`, replacement
`bar\1` — `\1`…`\9` reference capture groups, `&` is the whole match.

---

## 7. Files & buffers

| Shortcut | Action |
|---|---|
| `^O` | Save (write out) |
| `^X` | Exit; if modified, answer `Y` + filename, or `N` to discard |
| `^R` | **Read (insert) another file** into the current buffer at the cursor |
| `^R` then `^X` | Execute a shell command and insert its **output** |
| `^R` then `M-F` | Toggle: open the file in a **new buffer** instead of inserting |
| `M-<` / `M->` (or `M-,` / `M-.`) | Switch to previous / next open buffer |
| `^O` then `M-D` | Toggle DOS format (CRLF) on save |
| `^O` then `M-M` | Toggle Mac format on save |
| `^O` then `M-P` | Prepend instead of overwrite |
| `^O` then `M-A` | Append instead of overwrite |
| `^O` then `M-B` | Make a backup of the original |
| `^O` then `^T` | Browse the filesystem to pick a location ("To Files") |

**Run a command and capture output into your file:** `^R`, then `^X`, then type
e.g. `date` or `ls -la` and Enter — the output is inserted at the cursor. Great
for timestamps and boilerplate.

---

## 8. Display toggles (while editing)

| Shortcut | Action |
|---|---|
| `M-N` (older `M-#`) | Line numbers on/off |
| `M-S` | Soft-wrapping of long lines on/off |
| `M-P` | Show whitespace (tabs/spaces) on/off |
| `M-Y` | Syntax highlighting on/off |
| `M-X` | Help lines at the bottom on/off (more editing room) |
| `M-C` | Constant cursor-position display on/off |
| `M-H` | Smart Home key on/off |
| `M-I` | Auto-indent on/off |
| `M-M` | Mouse support on/off |
| `M-K` | Cut-to-end-of-line mode on/off |
| `M-O` | Tabs-to-spaces conversion on/off |
| `M-Z` | Suspend nano (return with `fg`) — or hide the interface in newer versions |

---

## 9. Multiple-line tricks & lesser-known gems

- **Cut multiple lines:** press `^K` repeatedly without moving — consecutive cuts
  accumulate in one cut buffer; a single `^U` pastes them all back.
- **Duplicate a line:** `M-6` (copy line), then `^U` (paste) — cursor stays put,
  so the pasted copy lands right below.
- **Move a line down/up:** `^K` (cut), move, `^U` (paste). Modern nano does not
  have a dedicated move-line shortcut by default, but you can bind one (below).
- **Column/vertical selection:** not supported — for column edits use
  search/replace with regex anchors (`^` / `$`) instead.
- **Anchor bookmarks:** `M-Insert` drops an anchor on the line; `M-PgUp` /
  `M-PgDn` jump between anchors (nano ≥ 5.0).
- **Word count:** `M-D` reports lines/words/characters of the file (or the
  marked region).
- **Indent an entire block:** mark it (`M-A` + move), then `Tab`.
- **Recover from a crash:** nano leaves `.filename.swp`-style emergency saves as
  `filename.save`; also see `-B`/`set backup` for `filename~` backups.
- **Full undo across saves:** undo history survives `^S`/`^O` within a session,
  so you can save early and often.

---

## 10. Configuration — `~/.nanorc`

Per-user settings live in `~/.nanorc` (system-wide: `/etc/nanorc`). A solid
starter:

```nanorc
set linenumbers        # show line numbers
set autoindent         # keep indentation on new lines
set tabsize 4          # tab display width
set tabstospaces       # insert spaces when Tab is pressed
set softwrap           # soft-wrap long lines
set atblanks           # ...wrapping at word boundaries
set constantshow       # always show cursor position
set indicator          # scrollbar-style position indicator
set smarthome          # Home toggles between text start and column 0
set mouse              # enable mouse clicks/selection
set historylog         # remember search/replace history across sessions
set positionlog        # reopen files at the last cursor position
set backup             # keep filename~ backups on save
set backupdir "~/.nano/backups"   # ...in one place (mkdir it first)
set afterends          # Ctrl+Right stops after word ends (word-hopping feel)
set zap                # typing over a marked region replaces it
set matchbrackets "(<[{)>]}"      # brackets for M-] matching
set titlecolor bold,white,blue    # cosmetic: title bar colors
set numbercolor cyan
set selectedcolor lightwhite,magenta
```

**Enable syntax highlighting** (paths vary slightly by distro):

```nanorc
include "/usr/share/nano/*.nanorc"
# extra community syntaxes, if installed:
# include "/usr/share/nano/extra/*.nanorc"
```

**Custom key bindings** — `bind <key> <function> <menu>`:

```nanorc
bind ^Q exit all              # Ctrl+Q quits, like other editors
bind ^F whereis all           # Ctrl+F to search
bind ^H replace all           # Ctrl+H to replace
bind ^Z undo main             # Ctrl+Z undoes (loses suspend)
bind ^Y redo main             # Ctrl+Y redoes
bind ^C copy main             # Ctrl+C copies marked region
bind ^V paste all             # Ctrl+V pastes
bind ^X cut all               # Ctrl+X cuts  (loses default exit binding!)
```

> Careful when rebinding `^X`/`^C` — you're overriding nano's exit/position
> keys. Keep `^Q → exit` bound if you take `^X` for cut.

List all current bindings from inside nano: `^G` (help shows the active keymap).

---

## 11. Handy command-line one-liners

```sh
nano ~/.nanorc                          # edit your own config
nano -w /etc/fstab                      # config-safe editing (no wrapping)
sudo nano /etc/hosts                    # root-owned files
nano +$(grep -n 'pattern' f | head -1 | cut -d: -f1) f   # open at first match
EDITOR=nano crontab -e                  # use nano for crontab editing
export EDITOR=nano VISUAL=nano          # make nano the default editor (put in ~/.bashrc)
sudo update-alternatives --config editor   # Debian/Ubuntu: set system default editor
nano -                                   # edit from stdin (pipe into nano)
```

---

## 12. Quick reference card

```
FILE                          EDIT                        SEARCH
^O  save                      M-U undo    M-E redo        ^W  find
^S  save, no prompt           ^K  cut line                ^\  find & replace
^X  exit                      M-6 copy line               M-W find next
^R  insert file/cmd output    ^U  paste                   (in prompt: M-C case,
M-< / M-> switch buffer       ^D  delete char              M-R regex, M-B back)
                              M-3 (un)comment
MOVE                          ^J  justify para            SELECT
^A / ^E  line start/end       ^T  spell check             M-A  set mark
^Y / ^V  page up/down         M-] match bracket           then move + ^K/M-6
M-\ / M-/ file top/bottom     Tab/S-Tab indent region     Shift+arrows also work
^_  go to line                ^]  word completion
^C  where am I                M-D word count              M-N line numbers
                                                          M-P show whitespace
```

---

## 13. Version notes

Shortcut sets shifted over the years (notably at nano 2.x → 4.x/5.x). If a
shortcut here doesn't work:

- Check your version: `nano --version`.
- Check the live keymap: `^G` inside nano always shows *your* build's bindings.
- Amazon Linux / older RHEL ship older nano (2.9.x) — `^S` quick-save, `M-N`
  line-number toggle, and anchors (`M-Insert`) need nano ≥ 4.x/5.x. The
  survival-kit shortcuts in section 1 work everywhere.
