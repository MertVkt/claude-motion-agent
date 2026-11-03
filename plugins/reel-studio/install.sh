#!/usr/bin/env bash
# reel-studio installer (macOS).
# Installs from their official sources: ffmpeg, HyperFrames skills, Mirage Tesseract (skills + pinned
# tsrct CLI with checksum verification), the HeyGen CLI, Blender, and the reel-studio Claude Code plugin.
# Safe to re-run: every step checks whether its tool is already present.
# Lives in <repo>/plugins/reel-studio/ and can be run from any folder.
#
# Usage:  bash install.sh [--skip-blender] [--skip-heygen] [--skip-hyperframes] [--dry-run]

set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PLUGIN_DIR/../.." && pwd)"
SKIP_BLENDER=0; SKIP_HEYGEN=0; SKIP_HF=0; DRY=0
for a in "$@"; do
  case "$a" in
    --skip-blender) SKIP_BLENDER=1 ;;
    --skip-heygen) SKIP_HEYGEN=1 ;;
    --skip-hyperframes) SKIP_HF=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done

say()  { printf "\n\033[1;33m==> %s\033[0m\n" "$*"; }
ok()   { printf "    \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "    \033[31m!\033[0m %s\n" "$*"; }
run()  { if [ "$DRY" = 1 ]; then echo "    [dry-run] $*"; else eval "$@"; fi; }

[ "$(uname -s)" = "Darwin" ] || { echo "This installer supports macOS only. On Windows/Linux install ffmpeg, the Tesseract skills and tsrct by hand (see SKILL.md)."; exit 1; }

# ---------------------------------------------------------------- prerequisites
say "Prerequisites"
if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew not found. Install it first (https://brew.sh), then re-run this script:"
  echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi
ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"
command -v python3 >/dev/null 2>&1 || run "xcode-select --install"
ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"
command -v ffmpeg >/dev/null 2>&1 || run "brew install ffmpeg"
ok "ffmpeg"
command -v node >/dev/null 2>&1 || run "brew install node"
ok "node $(node --version 2>/dev/null || echo '(installed)')"
command -v claude >/dev/null 2>&1 && ok "Claude Code CLI $(claude --version 2>/dev/null | head -1)" || ok "Claude Code CLI not on PATH (normal for Claude Desktop) - the plugin will be copied into ~/.claude/skills"

# ---------------------------------------------------------------- HyperFrames
if [ "$SKIP_HF" = 0 ]; then
  say "HeyGen HyperFrames skills (HTML video engine + SFX library used by reel-studio)"
  run "npx -y hyperframes@latest skills update"
  run "npx -y hyperframes@latest skills update general-video"
  [ -d "$HOME/.claude/skills/media-use" ] && ok "HyperFrames skills in ~/.claude/skills" || warn "media-use skill not found yet (check the output above)"
fi

# ---------------------------------------------------------------- Tesseract
say "Mirage Tesseract skills"
run "npx -y skills add mirage-hq/Tesseract -s '*' -a claude-code -g -y"

say "Mirage Tesseract CLI (tsrct)"
PIN_FILE="$HOME/.claude/skills/tesseract-video/references/cli-version.txt"
if [ -f "$PIN_FILE" ]; then VER="$(tr -d '[:space:]' < "$PIN_FILE")"; else VER="0.3.1"; warn "pin file missing, using $VER"; fi
TSRCT="$HOME/Library/Application Support/Tesseract/bin/tsrct"
if [ -x "$TSRCT" ] && "$TSRCT" --version 2>/dev/null | grep -q "tsrct $VER"; then
  ok "tsrct $VER already installed"
else
  ARCH="$(uname -m)"
  if [ "$(sysctl -in sysctl.proc_translated 2>/dev/null || echo 0)" = 1 ]; then ARCH=arm64; fi
  case "$ARCH" in arm64) PLAT=darwin-arm64 ;; x86_64) PLAT=darwin-x86_64 ;; *) echo "unsupported arch $ARCH"; exit 1 ;; esac
  ZIP="tesseract-$VER-$PLAT.zip"; URL="https://github.com/mirage-hq/tesseract/releases/download/v$VER"
  DL="$(mktemp -d)"
  run "curl -fL -o '$DL/$ZIP' '$URL/$ZIP'"
  run "curl -fL -o '$DL/$ZIP.sha256' '$URL/$ZIP.sha256'"
  run "(cd '$DL' && shasum -a 256 -c '$ZIP.sha256')"
  run "ditto -x -k '$DL/$ZIP' '$DL/x'"
  run "bash \"\$(ls -d '$DL'/x/*/ | head -1)install.sh\""
  [ "$DRY" = 1 ] || "$TSRCT" --version
  ok "tsrct $VER installed at: $TSRCT"
fi

# ---------------------------------------------------------------- HeyGen CLI
if [ "$SKIP_HEYGEN" = 0 ]; then
  say "HeyGen CLI (music library / TTS for HyperFrames)"
  if [ -x "$HOME/.local/bin/heygen" ] || command -v heygen >/dev/null 2>&1; then ok "heygen already installed"
  else run "curl -fsSL https://static.heygen.ai/cli/install.sh | bash"; fi
fi

# ---------------------------------------------------------------- Blender
if [ "$SKIP_BLENDER" = 0 ]; then
  say "Blender"
  if [ -d "/Applications/Blender.app" ]; then ok "Blender already installed"; else run "brew install --cask blender"; fi
fi

# ---------------------------------------------------------------- reel-studio plugin
say "reel-studio Claude Code plugin"
if command -v claude >/dev/null 2>&1 && [ "${REEL_COPY_PLUGIN:-0}" != 1 ] && [ -f "$REPO/.claude-plugin/marketplace.json" ]; then
  run "claude plugin marketplace add '$REPO' || true"
  run "claude plugin install reel-studio@claude-motion-agent"
  ok "plugin installed via marketplace (restart Claude Code to load it)"
else
  # Claude Desktop (Code tab) often has no `claude` CLI on PATH: install as a skills-dir plugin instead.
  # Claude Code auto-loads ~/.claude/skills/<name>/ (with .claude-plugin/plugin.json) as <name>@skills-dir.
  run "mkdir -p '$HOME/.claude/skills' && rm -rf '$HOME/.claude/skills/reel-studio' && cp -R '$PLUGIN_DIR' '$HOME/.claude/skills/reel-studio'"
  ok "plugin copied to ~/.claude/skills/reel-studio (loads in the next Claude Code / Claude Desktop session)"
fi

say "Done. Remaining steps that need YOUR accounts (browser sign-in):"
cat <<EOF
    1) HeyGen (music library, optional):   ~/.local/bin/heygen auth login --oauth
    2) HyperFrames / HeyGen (optional):     npx hyperframes auth login
    3) Restart Claude Code, then try:       "Make an effect-heavy Instagram reel from the clips in this folder"
EOF
