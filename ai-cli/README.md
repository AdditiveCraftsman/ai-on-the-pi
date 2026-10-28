# ai-cli — terminal chatbot for Raspberry Pi

A lightweight AI assistant you can use directly from the terminal on a Raspberry Pi. No browser required. Works on any Pi with internet access — including headless setups over SSH.

The heavy lifting happens on the cloud. Your Pi just sends text and receives text — minimal CPU and RAM usage.

---

## Why

Web-based AI interfaces (Claude.ai, Gemini, ChatGPT) are too demanding for Raspberry Pi browsers on 1GB RAM. A terminal-based client sidesteps the browser entirely.

---

## What's included

| File | Purpose |
|------|---------|
| `ai-cli-setup.sh` | Interactive installer — run this first |
| `gemini_cli.py` | Python chatbot client (Gemini only, pure stdlib) |
| `gemini_config.example.json` | System prompt template — copy and customise |

---

## Requirements

- Raspberry Pi (any model with internet access)
- Python 3.7+
- pip3
- An API key for your chosen provider

---

## Quick start

### 1. Clone or download

```bash
git clone https://github.com/YOUR_USERNAME/ai-on-the-pi.git
cd ai-on-the-pi/ai-cli
```

### 2. Run the installer

```bash
chmod +x ai-cli-setup.sh
./ai-cli-setup.sh
```

The installer will:
- Install the `llm` CLI tool via pip
- Fix `~/.local/bin` PATH if needed
- Let you choose a provider (see below)
- Install the right plugin
- Prompt you for your API key
- Create `ai` and `aic` aliases
- Run a connection test

> Run as your normal user — **not** sudo or root.

### 3. Set up your system prompt (optional but recommended)

```bash
cp gemini_config.example.json ~/.config/gemini-cli/config.json
nano ~/.config/gemini-cli/config.json
```

Edit the file to describe your setup, hardware, and any gotchas you want the AI to keep in mind. This is what makes the assistant context-aware for your specific environment.

### 4. Reload and test

```bash
source ~/.bashrc
ai "what is my current directory"
```

---

## Supported providers

| # | Provider | Cost | Model | Notes |
|---|----------|------|-------|-------|
| 1 | Google Gemini | **Free** (250 req/day, no credit card) | gemini-2.5-flash | Recommended starting point |
| 2 | OpenRouter | Free models available | varies | Needs account |
| 3 | Anthropic | Paid | claude-haiku-4-5 | Requires billing |
| 4 | OpenAI | Paid | gpt-4o-mini | Requires billing |

Get a free Gemini key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no credit card required.

> **Note:** Google's free tier may use your prompts to improve their models. Don't send passwords, API keys, or private data.

---

## Usage

### Single question (stateless)

```bash
ai "how do I check disk space"
```

### Pipe command output

```bash
dmesg | tail -20 | ai "any errors here?"
cat /etc/fstab | ai "explain this file"
journalctl -u nginx | tail -30 | ai "what is this service doing?"
```

### Interactive chat session (context preserved within session)

```bash
aic
```

Type `exit` to quit. Type `clear` to reset history within the session.

### Save and resume conversations

```bash
# Save history to disk
ai "question" --save

# Load saved history, ask a question, save back
ai "question" --continue --save

# Resume an interactive session with saved history
aic --continue --save
```

### Other commands

```bash
ai --models          # list the models your API key can use right now
ai --config          # show config file path and current settings
ai --clear-history   # delete saved history file
llm models           # list all available models
```

---

## The system prompt — `config.json`

The config file at `~/.config/gemini-cli/config.json` controls four things:

```json
{
  "model": "gemini-2.5-flash",
  "history_file": "~/.local/share/gemini-cli/history.json",
  "max_history_messages": 40,
  "system_prompt": "Your instructions here..."
}
```

**`model`** — which Gemini model to use. Google retires and renames models regularly, so run `ai --models` to see what your key can use today, then copy a name into this setting. Generally, "flash" models are the fast, cheap default, "flash-lite" models are faster still with higher free-tier limits, and "pro" models are the most capable with tighter limits. If a model is retired you will get a 404 error that points you back to `ai --models`.

**`max_history_messages`** — how many of the most recent messages are sent to the API when you use `--continue` or `--chat` (default 40; `0` sends everything). Older turns stay in your history file but are not sent, which keeps replies fast and cheap.

**`system_prompt`** — what the AI knows about you and your setup. This is where the assistant gets context-aware. See `gemini_config.example.json` for a starting template.

**`history_file`** — where conversation history is saved when using `--save`.

Network hiccups and free-tier rate limits (HTTP 429/503) are retried automatically, and a failed request in `--chat` no longer ends your session.

> Each Pi in a multi-Pi setup can have its own `config.json` with a different system prompt tailored to that Pi's role (e.g. an OctoPrint Pi's prompt could include printer model, G-code notes, common issues).

---

## API key storage

The installer stores your key via `llm keys set <provider>`. It also looks for a key file at `~/gemini-key.txt` as a fallback.

**Never commit your API key to Git.** The `.gitignore` in this repo excludes `*.key`, `gemini-key.txt`, and `config.json` (but not `*.example.json`).

If you need to update your key:

```bash
cat ~/gemini-key.txt | llm keys set gemini
```

---

## Switching providers

Re-run the installer and choose a different provider. It will update the plugin and aliases:

```bash
./ai-cli-setup.sh
```

---

## How it works

```
You (terminal)
     │
     ▼
gemini_cli.py   ←──  ~/.config/gemini-cli/config.json  (system prompt, model)
     │
     ▼
Google Gemini API  (all inference happens here — Pi does nothing heavy)
     │
     ▼
Response printed to terminal
```

For non-Gemini providers, `llm` handles the API call directly instead of `gemini_cli.py`.

---

## Tested on

- Raspberry Pi 3B (Rev 1.2), 1GB RAM, Pi OS Bookworm/Trixie
- Should work on any Pi model with Python 3.7+ and pip

---

## License

MIT — see [LICENSE](../LICENSE)
