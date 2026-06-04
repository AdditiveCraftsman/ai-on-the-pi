#!/bin/bash
# ============================================================
#  AI CLI Setup Script for Raspberry Pi 3B
#  Installs the `llm` CLI tool with user-chosen AI provider
#
#  Supported providers:
#    1. Google Gemini  (FREE — no credit card needed)
#    2. OpenRouter     (FREE models available — account needed)
#    3. Anthropic      (PAID — API key + billing required)
#    4. OpenAI         (PAID — API key + billing required)
#
#  Usage:
#    chmod +x ai-cli-setup.sh
#    ./ai-cli-setup.sh
#
#  What it does:
#    - Installs the `llm` Python CLI tool via pip
#    - Adds ~/.local/bin to PATH if needed
#    - Installs the plugin for your chosen AI provider
#    - Stores your API key securely
#    - Creates an `ai` alias for quick terminal access
#    - Tests the connection
#
#  Re-run safely to switch providers or update keys.
# ============================================================

set -e

# ── Colors ───────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $1"; }

# ── Preflight checks ────────────────────────────────────────
if [[ $EUID -eq 0 ]]; then
    fail "Do NOT run this as root/sudo. Run as your normal user."
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    fail "Python3 not found. Install it first: sudo apt install python3 python3-pip"
    exit 1
fi

if ! command -v pip &>/dev/null && ! command -v pip3 &>/dev/null; then
    fail "pip not found. Install it first: sudo apt install python3-pip"
    exit 1
fi

# Use pip3 if pip isn't available
PIP_CMD="pip"
command -v pip &>/dev/null || PIP_CMD="pip3"

echo ""
echo "============================================"
echo "  AI CLI Setup for Raspberry Pi"
echo "  Lightweight terminal chatbot — no browser"
echo "============================================"
echo ""

# ── Step 1: Install llm ─────────────────────────────────────
if command -v llm &>/dev/null; then
    ok "llm is already installed ($(llm --version))"
else
    info "Installing llm CLI tool..."
    $PIP_CMD install llm --break-system-packages --quiet
    ok "llm installed."
fi

# ── Step 2: Fix PATH ────────────────────────────────────────
LOCAL_BIN="$HOME/.local/bin"
if [[ -d "$LOCAL_BIN" ]] && [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    info "Adding $LOCAL_BIN to PATH..."
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    export PATH="$LOCAL_BIN:$PATH"
    ok "PATH updated in .bashrc"
elif ! command -v llm &>/dev/null; then
    # llm installed but still not found — force PATH
    info "Adding $LOCAL_BIN to PATH..."
    mkdir -p "$LOCAL_BIN"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    export PATH="$LOCAL_BIN:$PATH"
    ok "PATH updated in .bashrc"
else
    ok "PATH already includes $LOCAL_BIN"
fi

# Verify llm is now accessible
if ! command -v llm &>/dev/null; then
    fail "llm command still not found after PATH fix. Try: source ~/.bashrc && ./ai-cli-setup.sh"
    exit 1
fi

# ── Step 3: Choose provider ──────────────────────────────────
echo ""
echo "Choose your AI provider:"
echo ""
echo "  1) Google Gemini    [FREE — no credit card, 250+ queries/day]"
echo "  2) OpenRouter       [FREE models available — needs account]"
echo "  3) Anthropic Claude [PAID — requires API key + billing]"
echo "  4) OpenAI GPT       [PAID — requires API key + billing]"
echo ""
read -rp "Enter 1, 2, 3, or 4: " PROVIDER_CHOICE

case "$PROVIDER_CHOICE" in
    1)
        PROVIDER="gemini"
        PLUGIN="llm-gemini"
        KEY_NAME="gemini"
        DEFAULT_MODEL="gemini-2.5-flash"
        KEY_URL="https://aistudio.google.com/apikey"
        KEY_PREFIX="AIza"
        info "Selected: Google Gemini (FREE tier)"
        ;;
    2)
        PROVIDER="openrouter"
        PLUGIN="llm-openrouter"
        KEY_NAME="openrouter"
        DEFAULT_MODEL="openrouter/google/gemma-3-1b-it:free"
        KEY_URL="https://openrouter.ai/keys"
        KEY_PREFIX=""
        info "Selected: OpenRouter (free models available)"
        ;;
    3)
        PROVIDER="anthropic"
        PLUGIN="llm-anthropic"
        KEY_NAME="anthropic"
        DEFAULT_MODEL="claude-haiku-4-5"
        KEY_URL="https://console.anthropic.com/settings/keys"
        KEY_PREFIX="sk-ant"
        info "Selected: Anthropic Claude (PAID)"
        ;;
    4)
        PROVIDER="openai"
        PLUGIN=""
        KEY_NAME="openai"
        DEFAULT_MODEL="gpt-4o-mini"
        KEY_URL="https://platform.openai.com/api-keys"
        KEY_PREFIX="sk-"
        info "Selected: OpenAI (PAID)"
        ;;
    *)
        fail "Invalid choice. Run the script again."
        exit 1
        ;;
esac

# ── Step 4: Install plugin ───────────────────────────────────
if [[ -n "$PLUGIN" ]]; then
    info "Installing $PLUGIN plugin..."
    $PIP_CMD install "$PLUGIN" --break-system-packages --quiet
    ok "$PLUGIN installed."
else
    ok "OpenAI support is built into llm — no plugin needed."
fi

# ── Step 5: API key ──────────────────────────────────────────
echo ""
echo "Now we need your API key."
echo "Get one here: $KEY_URL"
echo ""

# Check if key already exists
EXISTING_KEYS=$(llm keys 2>/dev/null || echo "")
if echo "$EXISTING_KEYS" | grep -q "^${KEY_NAME}$"; then
    echo "A key named '$KEY_NAME' already exists."
    read -rp "Overwrite it? (y/n): " OVERWRITE
    if [[ "$OVERWRITE" != "y" && "$OVERWRITE" != "Y" ]]; then
        info "Keeping existing key."
        SKIP_KEY=true
    fi
fi

if [[ "$SKIP_KEY" != "true" ]]; then
    echo ""
    echo "Paste your API key below and press Enter:"
    if [[ -n "$KEY_PREFIX" ]]; then
        echo "(It should start with: ${KEY_PREFIX}...)"
    fi
    echo ""
    read -rp "API key: " API_KEY

    if [[ -z "$API_KEY" ]]; then
        fail "No key entered. You can set it later with: llm keys set $KEY_NAME"
    else
        echo "$API_KEY" | llm keys set "$KEY_NAME"
        ok "API key stored for $KEY_NAME."
    fi
fi

# ── Step 6: Install gemini_cli.py (Gemini only) + set aliases ─
sed -i '/^alias ai=/d'  "$HOME/.bashrc"
sed -i '/^alias aic=/d' "$HOME/.bashrc"

if [[ "$PROVIDER" == "gemini" ]]; then
    # Install gemini_cli.py — rich Python client with history,
    # config file, --save / --continue / --chat flags
    CLI_SCRIPT="$LOCAL_BIN/gemini_cli.py"
    SCRIPT_URL="https://raw.githubusercontent.com/your-repo/gemini_cli.py/main/gemini_cli.py"

    # Check if the script is sitting next to this installer
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$SCRIPT_DIR/gemini_cli.py" ]]; then
        cp "$SCRIPT_DIR/gemini_cli.py" "$CLI_SCRIPT"
        chmod +x "$CLI_SCRIPT"
        ok "Installed gemini_cli.py → $CLI_SCRIPT"
    else
        warn "gemini_cli.py not found next to this script."
        warn "Place gemini_cli.py in the same folder as ai-cli-setup.sh and re-run."
        warn "Falling back to basic llm aliases."
        CLI_SCRIPT=""
    fi

    if [[ -n "$CLI_SCRIPT" && -f "$CLI_SCRIPT" ]]; then
        # ai  = single question (no history by default)
        # aic = interactive chat session
        echo "alias ai=\"python3 $CLI_SCRIPT\"" >> "$HOME/.bashrc"
        echo "alias aic=\"python3 $CLI_SCRIPT --chat\"" >> "$HOME/.bashrc"
        alias ai="python3 $CLI_SCRIPT" 2>/dev/null || true
        alias aic="python3 $CLI_SCRIPT --chat" 2>/dev/null || true
        ok "Created alias: ai  → gemini_cli.py (single question)"
        ok "Created alias: aic → gemini_cli.py --chat (interactive, with history support)"
    else
        # Fallback to plain llm aliases
        echo "alias ai=\"llm -m $DEFAULT_MODEL\"" >> "$HOME/.bashrc"
        echo "alias aic=\"llm chat -m $DEFAULT_MODEL\"" >> "$HOME/.bashrc"
        alias ai="llm -m $DEFAULT_MODEL" 2>/dev/null || true
        alias aic="llm chat -m $DEFAULT_MODEL" 2>/dev/null || true
        ok "Created alias: ai  → llm -m $DEFAULT_MODEL"
        ok "Created alias: aic → llm chat -m $DEFAULT_MODEL"
    fi
else
    # Non-Gemini providers: plain llm aliases
    echo "alias ai=\"llm -m $DEFAULT_MODEL\"" >> "$HOME/.bashrc"
    echo "alias aic=\"llm chat -m $DEFAULT_MODEL\"" >> "$HOME/.bashrc"
    alias ai="llm -m $DEFAULT_MODEL" 2>/dev/null || true
    alias aic="llm chat -m $DEFAULT_MODEL" 2>/dev/null || true
    ok "Created alias: ai  → llm -m $DEFAULT_MODEL (single question)"
    ok "Created alias: aic → llm chat -m $DEFAULT_MODEL (interactive chat)"
fi

# ── Step 7: Test ─────────────────────────────────────────────
echo ""
info "Testing connection..."
echo ""

RESPONSE=$(llm -m "$DEFAULT_MODEL" "Reply with only the word WORKING" 2>&1 || true)

if echo "$RESPONSE" | grep -qi "working"; then
    ok "Connection successful!"
else
    warn "Got a response but it may not be right. Here's what came back:"
    echo "$RESPONSE"
    echo ""
    echo "If you see an API key error, re-run: llm keys set $KEY_NAME"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  Provider:  $PROVIDER"
echo "  Model:     $DEFAULT_MODEL"
echo "  Aliases:   ai  → single question"
echo "             aic → interactive chat (type 'exit' to quit)"
if [[ "$PROVIDER" == "gemini" ]]; then
echo ""
echo "  Gemini extras (gemini_cli.py):"
echo "    ai \"question\" --save        save history to disk"
echo "    ai \"question\" --continue    load history, then ask"
echo "    aic --save                  interactive + auto-save history"
echo "    aic --continue --save       resume + save persistent session"
echo "    ai --config                 show config file location"
echo "    ai --clear-history          delete saved history"
echo ""
echo "  Config: ~/.config/gemini-cli/config.json"
echo "  Edit to change model, system prompt, history path per Pi"
fi
echo ""
echo "  Usage:"
echo "    ai \"your question here\""
echo "    cat file.txt | ai \"explain this\""
echo "    aic  (opens interactive back-and-forth session)"
echo ""
echo "  To switch providers, re-run this script."
echo "  To change your key: llm keys set $KEY_NAME"
echo ""
echo "  Run 'source ~/.bashrc' or open a new terminal"
echo "  to activate the alias."
echo ""
