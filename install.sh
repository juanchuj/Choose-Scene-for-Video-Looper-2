#!/usr/bin/env bash
# install.sh - install Choose Scene for Video Looper 2 for the current user.
# Run as your normal user (not with sudo):  ./install.sh
set -e

if [ "$(id -u)" -eq 0 ]; then
  echo "Run ./install.sh as your normal user, without sudo." >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"

if ! command -v ffprobe >/dev/null; then
  echo ">> Installing ffmpeg (needs sudo) ..."
  sudo apt update && sudo apt install -y ffmpeg
fi

mkdir -p "$BIN" "$HOME/VideoLibrary"
install -m 755 "$DIR/choose_scene.py" "$BIN/choose_scene.py"

if ! echo ":$PATH:" | grep -q ":$BIN:"; then
  grep -qs 'HOME/.local/bin' "$HOME/.bashrc" || \
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  echo ">> Added ~/.local/bin to your PATH. Open a new terminal or run: source ~/.bashrc"
fi

echo
echo "Installed: $BIN/choose_scene.py"
echo "Scene library: $HOME/VideoLibrary  (add <Name>-Buffer.mp4 / <Name>-Scare.mp4 pairs)"
echo "Run: choose_scene.py"
