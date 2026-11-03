#!/bin/bash
# build.sh: compile the optional macOS helpers (Apple Vision / AppKit) into ./bin.
#   bash ~/.claude/skills/app-ad-video/scripts/macos/build.sh
# Needs macOS with the Xcode Command Line Tools (swiftc). vision.py also compiles facetrack on first use.
set -e
cd "$(dirname "$0")"
[ "$(uname)" = "Darwin" ] || { echo "these helpers need macOS (Apple Vision)"; exit 1; }
command -v swiftc >/dev/null || { echo "swiftc not found: xcode-select --install"; exit 1; }
mkdir -p bin
for t in facetrack ocr collage; do
  swiftc -O "$t.swift" -o "bin/$t" && echo "built bin/$t"
done
