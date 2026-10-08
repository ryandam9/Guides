#!/usr/bin/env bash
# Download community shader packs for Ghostty into ~/.config/ghostty/shaders,
# then list the available .glsl files so you can pick ones to enable with
# `custom-shader = shaders/...` in your Ghostty config.
set -euo pipefail

shader_dir="${XDG_CONFIG_HOME:-$HOME/.config}/ghostty/shaders"
mkdir -p "$shader_dir"

repos=(
  "https://github.com/0xhckr/ghostty-shaders"        # bloom, CRT, retro, water...
  "https://github.com/sahaj-b/ghostty-cursor-shaders" # cursor trails, ripple, pulse
)

for repo in "${repos[@]}"; do
  name="$(basename "$repo")"
  dest="$shader_dir/$name"
  if [ -d "$dest/.git" ]; then
    echo "Updating $name..."
    git -C "$dest" pull --quiet
  else
    echo "Cloning $name..."
    git clone --quiet --depth 1 "$repo" "$dest"
  fi
done

echo
echo "Available shaders (enable in your config with custom-shader = shaders/<path>):"
find "$shader_dir" -name '*.glsl' | sed "s|$shader_dir/|  shaders/|" | sort
