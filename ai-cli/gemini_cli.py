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
    "history_file": str(HISTORY_FILE)
}

API_URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/{model}:generateContent?key={key}"
)

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
def call_api(model, api_key, contents, system_prompt=None):
    url     = API_URL.format(model=model, key=api_key)
    payload = {"contents": contents}
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with Spinner():
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            msg = body
        err(f"API error ({e.code}): {msg}")
        sys.exit(1)
    except urllib.error.URLError as e:
        err(f"Network error: {e.reason}")
        sys.exit(1)

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        err(f"Unexpected API response: {result}")
        sys.exit(1)

# ── Single question mode ─────────────────────────────────────
def single_question(question, cfg, api_key, history, save, hist_file):
    history.append({"role": "user",  "parts": [{"text": question}]})
    response = call_api(cfg["model"], api_key, history, cfg.get("system_prompt"))
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
        response = call_api(cfg["model"], api_key, history, cfg.get("system_prompt"))
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
        "--config", action="store_true",
        help="Show config file path and current settings"
    )
    parser.add_argument(
        "--clear-history", action="store_true",
        help="Delete the saved history file"
    )

    args = parser.parse_args()
    cfg  = load_config()
    hist_file = cfg.get("history_file", str(HISTORY_FILE))

    # ── Info commands (no API needed) ────────────────────────
    if args.config:
        print(f"Config file   : {CONFIG_FILE}")
        print(f"History file  : {hist_file}")
        print(f"Model         : {cfg['model']}")
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

    if not args.chat and not args.question:
        parser.print_help()
        sys.exit(1)

    # ── Main flow ────────────────────────────────────────────
    api_key = load_api_key()
    history = load_history(hist_file) if args.cont else []

    if args.chat:
        chat_mode(cfg, api_key, history, args.save, hist_file)
    else:
        single_question(args.question, cfg, api_key, history, args.save, hist_file)


if __name__ == "__main__":
    main()
