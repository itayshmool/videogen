#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"

videogen "https://zero2claude.dev/" \
  --login-url "https://zero2claude.dev/login" \
  --username "testuser" \
  --password "telaviv18" \
  --no-headless \
  --keep-tmp \
  --landscape \
  --task "After logging in, navigate to the main dashboard. Screenshot the dashboard showing the lesson overview and progress. Then click into the first available level or lesson list and screenshot it. Open one lesson and screenshot the lesson content. If there are interactive elements like a terminal or exercises, screenshot those too. Capture 4-6 screenshots covering: dashboard, lesson list, lesson content, and any interactive features."
