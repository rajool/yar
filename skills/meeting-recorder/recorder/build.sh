#!/bin/bash
# build.sh — compile MeetingRecorder and package it as a minimal, ad-hoc-signed
#            .app bundle so macOS TCC grants (Microphone + Audio Recording) stick
#            to a stable bundle identity instead of the parent terminal.
#
# Output: <skill>/bin/MeetingRecorder.app   (git-ignored — source is committed, build is not)
#
# Requirements: swiftc + codesign (Xcode Command Line Tools). No full Xcode needed.

set -euo pipefail

RECORDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$RECORDER_DIR/.." && pwd)"
BIN_DIR="$SKILL_DIR/bin"
APP="$BIN_DIR/MeetingRecorder.app"
MACOS_DIR="$APP/Contents/MacOS"
BINARY="$MACOS_DIR/MeetingRecorder"
PLIST="$RECORDER_DIR/Info.plist"

err() { echo "ERROR: $*" >&2; exit 1; }

command -v swiftc   >/dev/null 2>&1 || err "swiftc not found. Install Xcode Command Line Tools: xcode-select --install"
command -v codesign >/dev/null 2>&1 || err "codesign not found (Xcode Command Line Tools)."

echo "[1/3] Compiling (embedding Info.plist for TCC identity)…" >&2
rm -rf "$APP"
mkdir -p "$MACOS_DIR"

# -sectcreate __TEXT __info_plist embeds the plist into the Mach-O so the binary
# carries its bundle identity + usage strings even when launched directly.
swiftc -O \
  "$RECORDER_DIR/main.swift" \
  -o "$BINARY" \
  -framework Foundation \
  -framework AVFoundation \
  -framework CoreAudio \
  -framework AudioToolbox \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$PLIST"

echo "[2/3] Assembling .app bundle…" >&2
cp "$PLIST" "$APP/Contents/Info.plist"

echo "[3/3] Ad-hoc code-signing…" >&2
codesign --force --sign - --identifier io.yar.meetingrecorder "$APP" >&2

echo "$APP"
echo "Built: $APP" >&2
