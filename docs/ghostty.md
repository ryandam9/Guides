# Ghostty — Making It Look Cool and Beautiful

## What it is

[Ghostty](https://ghostty.org/) is a fast, GPU-accelerated terminal emulator
by Mitchell Hashimoto. It is configured with a single plain-text file — no
GUI settings maze — and ships with ~400 built-in color themes, bundled Nerd
Font symbols, transparency/blur, and even custom GLSL shaders.

A ready-to-use config lives in this repo at
[`scripts/ghostty/config`](../scripts/ghostty/config). This guide explains
what's in it and what else you can tweak.

## Installing the config

```sh
mkdir -p ~/.config/ghostty
cp scripts/ghostty/config ~/.config/ghostty/config
```

Both macOS and Linux read `~/.config/ghostty/config`. Reload a running
Ghostty with `cmd+shift+,` (macOS) or `ctrl+shift+,` (Linux). Options that
affect the window frame (titlebar style, decorations) apply to *new*
windows.

Two commands worth knowing before you touch anything:

```sh
ghostty +list-themes    # interactive theme browser with live preview
ghostty +show-config --default --docs | less   # every option, documented
```

## The big visual wins

### 1. A cool dark theme

```ini
theme = Tokyonight Night
```

Tokyonight Night has a deep blue-black background (`#1a1b26`) with cold,
neon-leaning accents — the classic "cool dark" look. Since Ghostty 1.2
theme names are Title Case with spaces (`Tokyonight Night`, not
`tokyonight`) — always confirm the exact name in `ghostty +list-themes`.

Other favorites in the same mood: **Catppuccin Mocha** (soft pastels),
**Rose Pine** (muted, elegant), **Kanagawa Wave** (ink-painting vibes),
**Nord** (arctic blue-grey), **Challenger Deep** (dark purple).

Two useful variations:

```ini
# Even darker: an explicit background overrides the theme's own
background = #0d0e14

# Or follow the OS appearance instead of being always-dark
theme = light:Catppuccin Latte,dark:Tokyonight Night
```

### 2. A font with breathing room

```ini
font-family = JetBrains Mono
font-size = 13
adjust-cell-height = 10%
font-thicken = true          # macOS only: restores font weight
```

- Ghostty **bundles Nerd Font symbols** — use the plain font, and icons in
  tools like `eza`, starship, and neovim statuslines still render. No
  patched font needed.
- `adjust-cell-height = 10%` adds line spacing; it's the single cheapest
  readability upgrade there is.
- Other great monospace fonts: Fira Code, Cascadia Code, Monaspace Neon,
  Iosevka, Berkeley Mono (paid). Set italics/bold variants explicitly with
  `font-family-italic` etc. if a font family confuses auto-detection.
- Ligatures (`->`, `=>`, `!=` drawn as single glyphs) are on by default in
  fonts that have them; opt out per-feature with `font-feature = -calt`.

### 3. Frosted glass

```ini
background-opacity = 0.92
background-blur = 20
background-opacity-cells = false
minimum-contrast = 1.1
```

Opacity below ~0.85 starts hurting readability; `0.90–0.96` is the sweet
spot. The `background-blur` value is a blur radius — `20` gives the frosted
look. On Linux, blur needs a compositor that supports it (KDE/KWin does;
GNOME needs an extension). `minimum-contrast` is the safety net: Ghostty
will nudge any color combination so text never disappears into the
background.

### 4. Padding and a tidy window

```ini
window-padding-x = 12
window-padding-y = 12
window-padding-balance = true
window-padding-color = extend
```

Padding stops text from touching the window edge — the difference between
"default terminal" and "screenshot-ready". `extend` bleeds full-screen apps'
colors into the padding so there's no visible gutter.

On macOS, `macos-titlebar-style = tabs` puts tabs *inside* the titlebar —
the cleanest chrome Ghostty offers. (Alternatives: `transparent`, `native`,
`hidden`.) On Linux, `window-theme = ghostty` colors the GTK window chrome
to match your terminal theme.

## Quality-of-life settings

```ini
cursor-style = block
cursor-style-blink = false
cursor-click-to-move = true      # alt+click moves the cursor at the prompt
mouse-hide-while-typing = true
copy-on-select = clipboard       # select = copied, like classic X11 but to
                                 # the real clipboard
clipboard-paste-protection = true
scrollback-limit = 67108864       # bytes; renamed scrollback-limit-bytes in 1.4
window-save-state = always       # remember size/position
shell-integration-features = cursor,sudo,title
```

Shell integration is auto-injected for bash/zsh/fish and powers prompt
jumping (`cmd+up`/`cmd+down`), directory-aware new tabs, and the
bar-at-prompt cursor.

## The quick terminal

A drop-down terminal (Quake-style) that slides from the screen edge:

```ini
quick-terminal-position = top
keybind = global:cmd+grave_accent=toggle_quick_terminal   # macOS, system-wide
keybind = ctrl+grave_accent=toggle_quick_terminal          # Linux, in-app
```

The `global:` prefix makes it work from *any* app on macOS (grant the
Accessibility permission when asked). Press `` cmd+` `` anywhere and a
terminal drops down; press again and it slides away.

## Custom shaders (the party trick)

Ghostty can post-process the whole terminal with GLSL shaders — Shadertoy
format. People have built CRT curvature, bloom/glow, rain effects, and
animated "cursor smear" trails:

```ini
custom-shader = shaders/cursor_smear.glsl
custom-shader-animation = true
```

Good collections: [hackr-sh/ghostty-shaders](https://github.com/hackr-sh/ghostty-shaders)
(forked widely; search GitHub for "ghostty shaders" for more). Shader paths
are relative to the config file. Subtle ones (light bloom, cursor trail)
look fantastic; full CRT effects are fun for about a day.

There's also `background-image` (with `background-image-opacity` and
`background-image-fit`) if you want wallpaper behind your shell.

## Useful default keybinds

| Action | macOS | Linux |
| --- | --- | --- |
| New tab | `cmd+t` | `ctrl+shift+t` |
| Split right | `cmd+d` | `ctrl+shift+o` |
| Split down | `cmd+shift+d` | `ctrl+shift+e` |
| Move between splits | `cmd+opt+arrows` | `ctrl+alt+arrows` |
| Zoom a split | `cmd+shift+enter` | `ctrl+shift+enter` |
| Jump between prompts | `cmd+up` / `cmd+down` | — |
| Reload config | `cmd+shift+,` | `ctrl+shift+,` |
| Command palette | `cmd+shift+p` | `ctrl+shift+p` |

Custom binds use `keybind = trigger=action`; see all actions with
`ghostty +list-actions` and current binds with `ghostty +list-keybinds`.

## Troubleshooting

- **Theme name not found** — names are case-sensitive and changed in 1.2;
  copy the exact string from `ghostty +list-themes`.
- **Blur does nothing on Linux** — your compositor must support it (KWin
  does natively; GNOME needs the "Blur my Shell" extension).
- **"Unknown field" error** — the option doesn't exist in your installed
  version (e.g. `scrollback-limit-bytes` is the 1.4 name for what earlier
  versions call `scrollback-limit`). Check what your build supports with
  `ghostty +show-config --default --docs`.
- **Config seems ignored** — run `ghostty +show-config` to see what Ghostty
  actually loaded, and check for typos; unknown keys are reported at
  startup.
- **Global quick-terminal keybind dead on macOS** — System Settings →
  Privacy & Security → Accessibility → enable Ghostty.
