#!/usr/bin/env python3
"""
gemini_cli.py — Gemini terminal chatbot for Raspberry Pi
Pure stdlib — no extra pip installs required.

Usage:
  Single question:             gemini_cli.py "your question"
  Interactive chat:            gemini_cli.py --chat
  Single + save history:       gemini_cli.py "question" --save
  Interactive + save history:  gemini_cli.py --chat --save
  Load history + ask:          gemini_cli.py "question" --continue
  Load history + chat:         gemini_cli.py --chat --continue
  List usable models:          gemini_cli.py --models
  Try a model for one run:     gemini_cli.py -m MODEL "your question"
  Show config:                 gemini_cli.py --config
  Clear saved history:         gemini_cli.py --clear-history
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
CONFIG_DIR   = Path.home() / ".config"  / "gemini-cli"
CONFIG_FILE  = CONFIG_DIR  / "config.json"
DATA_DIR     = Path.home() / ".local"   / "share" / "gemini-cli"
HISTORY_FILE = DATA_DIR    / "history.json"
KEY_FILE     = Path.home() / "gemini-key.txt"

# ── Default config (written on first run) ───────────────────
DEFAULT_CONFIG = {
    "model": "gemini-2.5-flash",
    "system_prompt": (
        "You are a helpful Raspberry Pi and Linux assistant. "
        "Keep answers concise and practical. "
        "Prefer short commands over long explanations."
    ),
    "history_file": str(HISTORY_FILE),
    # Only the most recent N messages are sent to the API (keeps requests fast
    # and cheap when using --continue). 0 = send everything.
    "max_history_messages": 40
}

# GEMINI_API_BASE can be overridden (used for testing against a local server).
API_BASE = os.environ.get(
    "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
)
TIMEOUT_SEC = 90
RETRY_CODES = {429, 500, 502, 503, 504}
RETRY_DELAYS = [2, 5, 10]   # seconds between attempts

# ── Colors ───────────────────────────────────────────────────
def _tty():
    return sys.stdout.isatty()

GREEN  = "\033[0;32m"  if _tty() else ""
CYAN   = "\033[0;36m"  if _tty() else ""
YELLOW = "\033[1;33m"  if _tty() else ""
DIM    = "\033[2m"     if _tty() else ""
RESET  = "\033[0m"     if _tty() else ""

def info(msg):  print(f"{DIM}[info]{RESET} {msg}",  file=sys.stderr)
def warn(msg):  print(f"{YELLOW}[warn]{RESET} {msg}", file=sys.stderr)
def err(msg):   print(f"\033[0;31m[error]{RESET} {msg}", file=sys.stderr)

# ── Config ───────────────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    info(f"Created default config: {CONFIG_FILE}")
    info(f"Edit it to customise the system prompt or model.")
    return DEFAULT_CONFIG.copy()

# ── API key ──────────────────────────────────────────────────
def load_api_key():
    # 1. Environment variable
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key

    # 2. ~/gemini-key.txt (set up by ai-cli-setup.sh)
    if KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
        if key:
            return key

    # 3. llm keys database (fallback)
    llm_db = Path.home() / ".config" / "io.datasette.llm" / "keys.db"
    if llm_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(llm_db))
            row = conn.execute(
                "SELECT value FROM apikeys WHERE name='gemini'"
            ).fetchone()
            conn.close()
            if row and row[0].strip():
                return row[0].strip()
        except Exception:
            pass

    err(
        "No API key found.\n"
        "  Option 1: echo YOUR_KEY > ~/gemini-key.txt\n"
        "  Option 2: export GEMINI_API_KEY=YOUR_KEY"
    )
    sys.exit(1)

# ── History ──────────────────────────────────────────────────
def load_history(path):
    p = Path(path).expanduser()
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return []

def save_history(history, path):
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(history, f, indent=2)

def trim_history(history, max_messages):
    """Return the last max_messages messages, starting on a user turn."""
    if not max_messages or len(history) <= max_messages:
        return history
    trimmed = history[-max_messages:]
    while trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]
    return trimmed

# ── Spinner ──────────────────────────────────────────────────
class Spinner:
    def __init__(self, msg="Thinking"):
        self._msg   = msg
        self._stop  = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        i = 0
        while not self._stop.is_set():
            if sys.stderr.isatty():
                print(f"\r{DIM}{frames[i % len(frames)]} {self._msg}…{RESET}",
                      end="", file=sys.stderr, flush=True)
            i += 1
            time.sleep(0.08)
        if sys.stderr.isatty():
            print("\r" + " " * (len(self._msg) + 6) + "\r",
                  end="", file=sys.stderr, flush=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()

# ── API call ─────────────────────────────────────────────────
class ApiError(Exception):
    """A failed API call. Raised (not exited) so chat mode can survive it."""

def _retry_notice(what, attempt):
    warn(f"{what}; retrying in {RETRY_DELAYS[attempt]}s "
         f"({attempt + 1}/{len(RETRY_DELAYS)})")

def _request(url, api_key, payload=None):
    """One HTTP call with retries on rate limits / transient server errors."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"x-goog-api-key": api_key}   # key in a header, not the URL
    if data is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(len(RETRY_DELAYS) + 1):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                msg = json.loads(body).get("error", {}).get("message", body)
            except Exception:
                msg = body
            if e.code in RETRY_CODES and attempt < len(RETRY_DELAYS):
                _retry_notice(f"HTTP {e.code}", attempt)
                time.sleep(RETRY_DELAYS[attempt])
                continue
            hint = ""
            if e.code == 404:
                hint = ("\n  The model may have been retired or renamed. "
                        "Run:  gemini_cli.py --models")
            raise ApiError(f"API error ({e.code}): {msg}{hint}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            if attempt < len(RETRY_DELAYS):
                _retry_notice(f"network error ({reason})", attempt)
                time.sleep(RETRY_DELAYS[attempt])
                continue
            raise ApiError(f"Network error: {reason}")

def call_api(model, api_key, contents, system_prompt=None):
    url     = f"{API_BASE}/models/{model}:generateContent"
    payload = {"contents": contents}
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    with Spinner():
        result = _request(url, api_key, payload)

    block = result.get("promptFeedback", {}).get("blockReason")
    if block:
        raise ApiError(f"Request blocked by the API ({block}). Try rewording.")
    try:
        cand  = result["candidates"][0]
        parts = cand.get("content", {}).get("parts", [])
    except (KeyError, IndexError):
        raise ApiError(f"Unexpected API response: {result}")
    text = "".join(p.get("text", "") for p in parts)
    if not text:
        reason = cand.get("finishReason", "unknown")
        raise ApiError(f"Empty response (finishReason: {reason}).")
    return text

def list_models(api_key):
    """Print the models this API key can use for chat, newest listing first."""
    names, token = [], None
    while True:
        url = f"{API_BASE}/models?pageSize=200"
        if token:
            url += f"&pageToken={token}"
        page = _request(url, api_key)
        for m in page.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                names.append((m["name"].split("/", 1)[-1],
                              m.get("displayName", "")))
        token = page.get("nextPageToken")
        if not token:
            break
    return sorted(names)

# ── Single question mode ─────────────────────────────────────
def single_question(question, cfg, api_key, history, save, hist_file):
    history.append({"role": "user",  "parts": [{"text": question}]})
    try:
        response = call_api(cfg["model"], api_key,
                            trim_history(history, cfg.get("max_history_messages")),
                            cfg.get("system_prompt"))
    except ApiError as e:
        err(str(e))
        sys.exit(1)
    print(response)
    history.append({"role": "model", "parts": [{"text": response}]})
    if save:
        save_history(history, hist_file)
        info(f"History saved → {hist_file}")

# ── Interactive chat mode ────────────────────────────────────
def chat_mode(cfg, api_key, history, save, hist_file):
    model = cfg["model"]
    print(
        f"{DIM}Gemini chat  │  model: {model}"
        f"  │  type 'exit' to quit  │  'clear' to reset history{RESET}",
        file=sys.stderr
    )
    if history:
        exchanges = sum(1 for m in history if m["role"] == "user")
        info(f"Loaded {exchanges} previous exchange(s) from {hist_file}")
    print(file=sys.stderr)

    while True:
        try:
            user_input = input(f"{GREEN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}[exited]{RESET}", file=sys.stderr)
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("exit", "quit", "q"):
            break
        if cmd == "clear":
            history = []
            info("History cleared for this session.")
            continue
        if cmd == "save":
            save_history(history, hist_file)
            info(f"History saved → {hist_file}")
            continue
        if cmd in ("help", "?"):
            print(
                f"  {DIM}exit / quit{RESET}  — end session\n"
                f"  {DIM}clear{RESET}        — reset conversation history\n"
                f"  {DIM}save{RESET}         — save history to disk now\n",
                file=sys.stderr
            )
            continue

        history.append({"role": "user", "parts": [{"text": user_input}]})
        try:
            response = call_api(cfg["model"], api_key,
                                trim_history(history, cfg.get("max_history_messages")),
                                cfg.get("system_prompt"))
        except ApiError as e:
            err(str(e))
            history.pop()   # drop the unanswered question; the session continues
            continue
        print(f"\n{CYAN}Gemini:{RESET} {response}\n")
        history.append({"role": "model", "parts": [{"text": response}]})

        if save:
            save_history(history, hist_file)

    if save:
        save_history(history, hist_file)
        info(f"History saved → {hist_file}")

# ── Entry point ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="gemini_cli.py",
        description="Gemini terminal chatbot for Raspberry Pi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  gemini_cli.py "how do I check cpu temp"       single question
  gemini_cli.py --chat                           interactive chat
  gemini_cli.py "question" --save               save history to disk
  gemini_cli.py "question" --continue           load history, then ask
  gemini_cli.py --chat --continue --save        full persistent session
  gemini_cli.py --models                         list models your key can use
  gemini_cli.py -m gemini-flash-latest "question"   try another model once
  gemini_cli.py --config                         show config path + values
  gemini_cli.py --clear-history                  delete saved history
        """
    )

    parser.add_argument(
        "question", nargs="?",
        help="Question to ask (omit when using --chat)"
    )
    parser.add_argument(
        "--chat",  action="store_true",
        help="Start interactive back-and-forth session"
    )
    parser.add_argument(
        "--save",  action="store_true",
        help="Persist conversation history to disk"
    )
    parser.add_argument(
        "--continue", dest="cont", action="store_true",
        help="Load saved history before asking / chatting"
    )
    parser.add_argument(
        "-m", "--model", metavar="NAME",
        help="Use this model for this run (overrides config), e.g. -m gemini-flash-latest"
    )
    parser.add_argument(
        "--models", action="store_true",
        help="List the models your API key can use (to pick or update 'model')"
    )
    parser.add_argument(
        "--config", action="store_true",
        help="Show config file path and current settings"
    )
    parser.add_argument(
        "--clear-history", action="store_true",
        help="Delete the saved history file"
    )

    args = parser.parse_args()
    cfg  = load_config()
    if args.model:
        cfg["model"] = args.model
    hist_file = cfg.get("history_file", str(HISTORY_FILE))

    # ── Info commands (no API needed) ────────────────────────
    if args.config:
        print(f"Config file   : {CONFIG_FILE}")
        print(f"History file  : {hist_file}")
        print(f"Model         : {cfg['model']}")
        print(f"History limit : {cfg.get('max_history_messages')} messages")
        print(f"System prompt :\n  {cfg.get('system_prompt', '(none)')}")
        return

    if args.clear_history:
        p = Path(hist_file).expanduser()
        if p.exists():
            p.unlink()
            print(f"Deleted: {p}")
        else:
            print("No history file found.")
        return

    if not args.chat and not args.question and not args.models:
        parser.print_help()
        sys.exit(1)

    # ── Main flow ────────────────────────────────────────────
    api_key = load_api_key()

    if args.models:
        try:
            models = list_models(api_key)
        except ApiError as e:
            err(str(e))
            sys.exit(1)
        for name, display in models:
            mark = "  <- current" if name == cfg["model"] else ""
            print(f"{name:<40} {display}{mark}")
        info("Set your choice with:  \"model\": \"<name>\"  in " + str(CONFIG_FILE))
        return

    history = load_history(hist_file) if args.cont else []

    if args.chat:
        chat_mode(cfg, api_key, history, args.save, hist_file)
    else:
        single_question(args.question, cfg, api_key, history, args.save, hist_file)


if __name__ == "__main__":
    main()
