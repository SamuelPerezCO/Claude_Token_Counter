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

## Install it, step by step

Never used Python or a terminal before? Follow these five steps in order. It
takes about five minutes, and you only do it once.

### Step 1 — Install Python

1. Go to **<https://www.python.org/downloads/>**
2. Click the big yellow **Download Python** button
3. Open the file you just downloaded
4. ⚠️ **On the first screen, tick the box at the bottom that says
   "Add python.exe to PATH".** This is the step everyone forgets, and nothing
   works without it
5. Click **Install Now** and wait for it to finish

### Step 2 — Download this project

1. Scroll to the top of this page
2. Click the green **Code** button, then **Download ZIP**
3. Open your **Downloads** folder and find the ZIP file
4. Right-click it → **Extract All…** → **Extract**

### Step 3 — Build the app

1. Open the folder that was just extracted
2. Double-click **`build.bat`**
3. A black window opens and text scrolls past — this takes a minute or two
4. Wait until you see **`Built ... claude-meter.exe`**, then press any key to close

> Use `build.bat`, **not** `build_exe.ps1`. Windows blocks PowerShell scripts
> that were downloaded from the internet; the `.bat` file works around that.

### Step 4 — Run it

1. Open the new **`dist`** folder
2. Double-click **`claude-meter.exe`**
3. If Windows says *"Windows protected your PC"*, click **More info** →
   **Run anyway**. That warning appears because the app isn't signed, not
   because anything is wrong with it
4. A window opens showing a web address and a QR code — leave it open

### Step 5 — Open it on your phone

1. Point your phone's camera at the QR code
2. Tap the link that pops up
3. Your phone must be on the **same Wi-Fi** as your computer

That's it. To use it again later, just double-click `claude-meter.exe` — steps
1 to 3 are only needed once.

### If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `Python is not installed` | Step 1 didn't finish, or the PATH box wasn't ticked | Reinstall Python, tick **Add python.exe to PATH**, then close and reopen the black window |
| `running scripts is disabled on this system` | You ran `build_exe.ps1` instead of `build.bat` | Double-click **`build.bat`** |
| *Windows protected your PC* | The app isn't signed | **More info** → **Run anyway** |
| `No Claude Code OAuth credentials found` | You've never signed into Claude Code on this computer | Open Claude Code, sign in once, then restart the app |
| The phone page won't open | The phone is on a different network | Put both devices on the same Wi-Fi |
| `Could not bind ... address already in use` | Another program is using that port | Run `claude-meter.exe --port 9000` |

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

If PowerShell refuses to run the script, double-click `build.bat` instead — it
invokes the same script with the execution policy bypassed.

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
