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

Reload a running Ghostty with `cmd+shift+,`. Options that affect the
window frame (titlebar style, decorations) apply to *new* windows.

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
font-thicken = true          # restores the weight macOS renders too thin
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
look. `minimum-contrast` is the safety net: Ghostty will nudge any color
combination so text never disappears into the background.

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

`macos-titlebar-style = tabs` puts tabs *inside* the titlebar — the
cleanest chrome Ghostty offers. (Alternatives: `transparent`, `native`,
`hidden`.)

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
keybind = global:cmd+grave_accent=toggle_quick_terminal   # system-wide
```

The `global:` prefix makes it work from *any* app (grant the Accessibility
permission when asked). Press `` cmd+` `` anywhere and a terminal drops
down; press again and it slides away.

## Custom shaders (the party trick)

Ghostty can post-process the whole terminal with GLSL shaders — Shadertoy
format. People have built CRT curvature, bloom/glow, rain effects, and
animated cursor trails that smear behind the cursor as it moves.

Run [`scripts/ghostty/get-shaders.sh`](../scripts/ghostty/get-shaders.sh)
to download two good community packs into `~/.config/ghostty/shaders`
([0xhckr/ghostty-shaders](https://github.com/0xhckr/ghostty-shaders) for
bloom/CRT/retro effects, [sahaj-b/ghostty-cursor-shaders](https://github.com/sahaj-b/ghostty-cursor-shaders)
for cursor trails and ripples) — it lists every `.glsl` file it installed.
Then enable your picks:

```ini
custom-shader = shaders/ghostty-shaders/bloom.glsl
custom-shader = shaders/ghostty-cursor-shaders/trail.glsl
custom-shader-animation = always
```

Multiple `custom-shader` lines stack, paths are relative to the config
file, and cursor-trail shaders need `custom-shader-animation = always`
(they animate even when nothing is being typed). Most shaders expose
tweakable parameters — color, trail duration, thickness — as constants at
the top of the file. Subtle ones (light bloom, cursor trail) look
fantastic; full CRT effects are fun for about a day.

## Going further

### Leader-key keybinds (tmux-style)

`>` chains keys into a sequence — press the first combo, release, press
the next key:

```ini
keybind = cmd+s>d=new_split:right
keybind = cmd+s>shift+d=new_split:down
keybind = cmd+s>z=toggle_split_zoom
keybind = cmd+s>e=equalize_splits
```

Prefixes add superpowers: `global:` makes a bind work system-wide even
when Ghostty isn't focused, `performable:` only swallows the key when the
action can actually run, `all:` targets every open terminal at once, and
`unconsumed:` runs the action *and* still delivers the key to the shell.

### Custom command-palette entries

`cmd+shift+p` opens a searchable palette of every action. Add your own:

```ini
command-palette-entry = title:Reset Font Style, action:csi:0m
command-palette-entry = title:"Ghost", description:"Summon a ghost", action:"text:\xf0\x9f\x91\xbb"
```

Any keybind action works (`text:`, `csi:`, `new_split:right`, ...), so
rarely-used operations can live in the palette instead of eating a
keybind.

### Wallpaper inside the terminal

```ini
background-image = ~/Pictures/wallpaper.jpg
background-image-opacity = 0.08
background-image-fit = cover
```

Keep the opacity very low (0.05–0.15) — it reads as texture, not a
picture, and text stays legible. Combines with `background-opacity`.

### Split and color styling

```ini
split-divider-color = #3b4261     # divider matches the theme
unfocused-split-fill = #16161e    # tint used to fade unfocused splits
bold-color = bright               # bold text uses the bright palette
cursor-color = #7aa2f7            # force a cursor color over the theme
cursor-opacity = 0.85             # cursor never fully hides its glyph
palette = 4=#82aaff               # override any of the 16 ANSI colors
```

### A themed Dock icon

```ini
macos-icon = custom-style
macos-icon-ghost-color = #7aa2f7
macos-icon-screen-color = #1a1b26
```

Recolors the actual app icon — a Tokyonight-blue ghost on a dark screen.
Takes effect after restarting the app. (This one is active in the repo
config.)

### Odds and ends

```ini
alpha-blending = linear-corrected     # alternative glyph blending; try it
bell-features = attention, title, border  # visual bell instead of sound
mouse-scroll-multiplier = 2           # faster wheel scrolling
window-title-font-family = SF Pro     # different font for tab titles
macos-non-native-fullscreen = true    # fullscreen without a macOS Space
quick-terminal-animation-duration = 0.15  # snappier drop-down
```

## Useful default keybinds

| Action | Keys |
| --- | --- |
| New tab | `cmd+t` |
| Split right | `cmd+d` |
| Split down | `cmd+shift+d` |
| Move between splits | `cmd+opt+arrows` |
| Zoom a split | `cmd+shift+enter` |
| Jump between prompts | `cmd+up` / `cmd+down` |
| Reload config | `cmd+shift+,` |
| Command palette | `cmd+shift+p` |

Custom binds use `keybind = trigger=action`; see all actions with
`ghostty +list-actions` and current binds with `ghostty +list-keybinds`.

## Troubleshooting

- **Theme name not found** — names are case-sensitive and changed in 1.2;
  copy the exact string from `ghostty +list-themes`.
- **"Unknown field" error** — the option doesn't exist in your installed
  version (e.g. `scrollback-limit-bytes` is the 1.4 name for what earlier
  versions call `scrollback-limit`). Check what your build supports with
  `ghostty +show-config --default --docs`.
- **Config seems ignored** — run `ghostty +show-config` to see what Ghostty
  actually loaded, and check for typos; unknown keys are reported at
  startup.
- **Global quick-terminal keybind dead on macOS** — System Settings →
  Privacy & Security → Accessibility → enable Ghostty.
