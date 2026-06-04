# ai-on-the-pi

Tools and scripts for running AI assistants on Raspberry Pi hardware — no browser, no heavy dependencies, no cloud lock-in.

Built and tested on a 7-unit Raspberry Pi 3B home lab. Everything here is designed for low-RAM single-board computers where browser-based AI interfaces don't work.

---

## Projects

### [ai-cli](./ai-cli/)

A terminal-based AI chatbot for Raspberry Pi. Supports Google Gemini (free), OpenRouter (free models), Anthropic, and OpenAI. Single question mode, interactive chat, persistent history, and a context-aware system prompt you configure per device.

**Get started → [ai-cli/README.md](./ai-cli/README.md)**

---

## Requirements

- Raspberry Pi (any model with internet access)
- Python 3.7+
- pip3

Tested on Raspberry Pi 3B Rev 1.2, Pi OS Bookworm and Trixie (Debian 12/13).

---

## License

MIT License — free to use, modify, and distribute. See [LICENSE](./LICENSE).
