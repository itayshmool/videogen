# Login Fix Spec

## Problem
videogen needs to support sites behind login (e.g. zero2claude.dev). The original code had two issues:
1. No persistent browser sessions — user had to log in every run
2. Manual `BrowserSession` + `page.goto()` approach failed because browser-use's CDP WebSocket reconnects on startup, invalidating page handles

## Solution
Let the **Agent handle navigation internally** via `initial_actions` (it auto-extracts URLs from the task), and use a step callback to pause for login after the page loads.

## What Changed

### `src/videogen/config.py`
- Added `PROFILE_DIR = PROJECT_ROOT / ".browser-profile"` for persistent browser data

### `src/videogen/browser.py`
- **Removed** separate `BROWSE_TASK` vs `BROWSE_TASK_NO_LOGIN` — now single `BROWSE_TASK` template with `{url}` placeholder (Agent extracts URL and navigates via `initial_actions`)
- **Removed** `_login_and_create_session()` — manual BrowserSession approach didn't work (CDP WebSocket drops page handles)
- **Added** `_make_login_pause_callback()` — pauses at step 1 (after Agent's initial navigation completes) for user to log in
- **Added** `user_data_dir` to ALL `BrowserProfile` calls — persists cookies/localStorage to `.browser-profile/`
- **Added** `profile_dir` parameter to `browse_product()`
- Login flow: Agent navigates -> step callback fires at step 1 -> user logs in -> presses ENTER -> agent continues
- Non-login flow: Agent navigates with saved cookies from previous login

### `src/videogen/cli.py`
- Added `--profile / -p` CLI option (defaults to `.browser-profile/`)
- Passes `profile_dir` through to `browse_product()`

### `.gitignore`
- Added `.browser-profile/`

### `tests/test_browser.py`
- Rewrote tests for new API (48 tests, all passing)

## Usage
```bash
# First time — log in manually, cookies saved to .browser-profile/
.venv/bin/videogen "https://zero2claude.dev/" --login

# Subsequent runs — reuses saved session, no login needed
.venv/bin/videogen "https://zero2claude.dev/"
```

## Status
- All 48 tests pass
- Code is changed but NOT committed yet
- NOT tested end-to-end yet — browser opens but we haven't confirmed login + browse flow works (Mac restart interrupted testing)

## Next Steps
1. Run `.venv/bin/videogen "https://zero2claude.dev/" --login` and verify browser navigates to URL
2. Log in, press ENTER, confirm agent scrolls and captures screenshots
3. Run again WITHOUT `--login` to confirm cookies persist
4. Commit and push
