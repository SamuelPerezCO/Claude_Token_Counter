[Español](README.md) · **English**

# Claude Token Counter

A local usage meter for Claude Code. Run the `.exe`, scan the QR code it prints,
and watch your session and weekly rate-limit usage from your phone.

Inspired by [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter), which
shows the same numbers on an ESP32 desk display. This replaces the hardware with
a small local web server, so anything with a browser works.

```
  Claude Code Usage Meter v1.0.0
  polling Anthropic every 60s

  On this computer:  http://localhost:8765
  On your phone:     http://192.168.1.10:8765

  Phone must be on the same Wi-Fi network.

  Scan to open on your phone:

  █▀▀▀▀▀▀▀█ ▀▀█▀██▀███▀▀▀▀▀▀▀█
  █ █▀▀▀█ █ █   ██▀▀▀ █ █▀▀▀█ █
  ...
```

## How it works

There is no usage endpoint in the Claude API. The numbers live in the **response
headers** of any ordinary request, so this app:

1. Reads your Claude Code OAuth token from `~/.claude/.credentials.json`
2. Sends the smallest possible request to `POST /v1/messages`
   (`claude-haiku-4-5`, `max_tokens: 1`, body `"hi"`) and discards the reply
3. Parses the rate-limit headers that came back:

| Header | Meaning |
|---|---|
| `anthropic-ratelimit-unified-status` | `allowed` / `allowed_warning` / `rejected` |
| `anthropic-ratelimit-unified-5h-utilization` | session usage, as a fraction (`0.21` = 21%) |
| `anthropic-ratelimit-unified-5h-reset` | session reset, Unix epoch seconds |
| `anthropic-ratelimit-unified-7d-utilization` | weekly usage, as a fraction |
| `anthropic-ratelimit-unified-7d-reset` | weekly reset, Unix epoch seconds |
| `anthropic-ratelimit-unified-overage-utilization` | overage usage, if your plan has one |
| `anthropic-ratelimit-unified-representative-claim` | which window is currently binding |

Auth uses `Authorization: Bearer <token>` plus the `anthropic-beta:
oauth-2025-04-20` header — an OAuth token will **not** work as `x-api-key`.

**Cost:** each poll is ~8 input tokens and 1 output token on Haiku. At the default
60-second interval that is a rounding error, but it is not literally zero, and the
probe request itself counts toward the limits it reports.

## Running it

The built `.exe` is **not** in this repository — binaries don't belong in git, so
`dist/` is ignored. That means `build_exe.ps1` on its own does nothing: it is a
build script, and it compiles the source sitting next to it. You need the whole
repo either way.

### Build the .exe (needs Python once)

```powershell
git clone https://github.com/SamuelPerezCO/Claude_Token_Counter.git
cd Claude_Token_Counter
.\build_exe.ps1          # produces dist\claude-meter.exe
.\dist\claude-meter.exe
```

Python is needed only to *build*. The resulting executable is self-contained, so
the machine that runs it needs nothing installed.

### Or run from source directly

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m claude_meter
```

### Sharing it with someone else

Send them the built `dist\claude-meter.exe` and nothing else — it has no
dependencies. Two things worth telling them:

- **Windows SmartScreen will warn on first run.** The executable is unsigned, so
  Windows shows *"Windows protected your PC"* until they click **More info →
  Run anyway**. Removing that warning requires a paid code-signing certificate.
- **It reads their own credentials, not yours.** No token is baked into the
  binary. Whoever runs it sees *their* usage, from *their*
  `~/.claude/.credentials.json`, and they need to have logged into Claude Code
  at least once for it to work.

### Options

| Flag | Default | Notes |
|---|---|---|
| `--port N` | `8765` | Change if something already owns the port |
| `--host ADDR` | `0.0.0.0` | Use `127.0.0.1` to keep it off the network entirely |
| `--interval N` | `60` | Seconds between polls |
| `--open` | off | Open the dashboard in your browser at startup |
| `--no-qr` | off | Skip the QR code |
| `--verbose` | off | Log every HTTP request |

## Prerequisites

You must have logged into Claude Code at least once, so that
`~/.claude/.credentials.json` exists. If the token has expired, run `claude` once
to refresh it — this app deliberately never refreshes or writes to that file.

Point `CLAUDE_CREDENTIALS_PATH` at the file if it lives somewhere unusual.

## A note on network exposure

By default this binds to `0.0.0.0`, which is what makes the phone access work — it
means **anyone on your local network can open the dashboard**. There is no
authentication.

What they would see: your usage percentages and reset times. What they cannot get:
your OAuth token, which never leaves the host process and is never included in any
HTTP response. Still, on an untrusted network (café, coworking, hotel), run with
`--host 127.0.0.1` and use it only on that machine.

## Endpoints

| Route | Purpose |
|---|---|
| `/` | The dashboard |
| `/api/usage` | Current snapshot as JSON |
| `/api/refresh` | Ask the poller to fetch immediately |
| `/healthz` | Liveness check |

## The dashboard

Styled in Claude's palette — warm cream surfaces, orange accent, Styrene/Tiempos
typography. Three design notes, since each was a deliberate call:

- **The accent is `#cc785c`, not `#d97757`.** The more familiar Claude orange
  measures 2.96:1 against the cream surface, just under the 3:1 legibility bar;
  the "book cloth" step clears it. Dark mode uses `#d97757`, which passes against
  the darker surface.
- **All numerals are sans, even though headings are serif.** Styrene and Tiempos
  are commercially licensed and can't be embedded, so they're named first in the
  font stack with fallbacks. Georgia — the likely Tiempos fallback — has
  old-style figures where 3, 4, 5, 7 and 9 drop below the baseline, which would
  make a large percentage visibly wobble.
- **Status never relies on colour alone.** The "Allowed" green and "Rate limited"
  red are near-identical under deuteranopia (ΔE 4.1), so the status pill always
  carries an icon *and* a word.

Usage is shown as meters rather than gauges or pie charts: the data is a single
ratio against a limit, which is what a meter is for.

## Layout

```
claude_meter/
  __main__.py      CLI, startup banner, QR code
  credentials.py   finds and reads the OAuth token
  usage.py         the probe request + header parsing + polling thread
  server.py        the HTTP server
  netinfo.py       LAN IP discovery, QR rendering
  static/
    index.html     the dashboard (single file, no build step)
```

The dashboard polls `/api/usage` every 5 seconds, but that only reads a cached
snapshot on the host — Anthropic is contacted on the `--interval` timer, not per
page view. Countdowns tick client-side and are corrected against the host's clock,
so they stay right even if your phone's time is off.
