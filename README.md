# DeckVoice

GPU push-to-talk voice input for Steam Deck (Decky Loader). Hold a trigger combo, release to type into the focused game chat.

## Layout

```
main.py                 # Decky entry (bootstrap)
deckvoice/              # Python package
  plugin.py             # Plugin RPC / lifecycle
  voice_service.py      # Whisper + mic + ydotool
  controller_listener.py
  deck_hid.py
src/                    # QAM frontend (TypeScript)
defaults/               # game presets, channel languages
backend/                # Docker build → bin/
  Dockerfile
  entrypoint.sh
  requirements.txt
tests/
```

## Features

- **Trigger combo** (default L1+R1) via raw Steam Deck HID
- Chat insert on release
- **Enable** fully starts/stops `whisper-server` (Vulkan), HID listener, and `ydotoold` so VRAM is free when off
- Model size and language in QAM
- Game profiles: **World of Warcraft** (`party hello` → `/p hello`) and **Generic**

## Requirements

- Steam Deck, Game Mode, [Decky Loader](https://decky.xyz)
- SSH enabled for deploy (`Settings → System → Enable SSH`)

## Dev loop

```bash
make test
npm install && npm run build
make bin      # linux/amd64 Docker build
make deploy   # deck@192.168.1.216
make logs
```

First Enable downloads a ggml model into Decky settings (`models/`).

## Smoke checklist (on Deck)

1. QAM → DeckVoice → Enable
2. Hold Trigger combo → toast with live text
3. Release → typed into chat (WoW: Enter, `/p …`, Enter)
4. Disable → VRAM freed

## License

MIT (plugin). Bundled `ydotool` is AGPL-3.0; whisper.cpp is MIT. See `bin/licenses` after build.
