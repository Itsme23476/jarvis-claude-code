#!/usr/bin/env bash
# Launch the JARVIS memory HUD. Keeps Homebrew/user bins on PATH so a
# GUI-launched shell can still find `claude`.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$PATH"
exec python3 server.py
