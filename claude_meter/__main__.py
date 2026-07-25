"""Entry point: start the poller, start the server, print the URL and a QR code."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import threading
import webbrowser

from . import __version__, netinfo
from .server import make_server
from .usage import Poller

DEFAULT_PORT = 8765


def _enable_ansi() -> bool:
    """Turn on VT processing on Windows consoles. Returns True if colour is usable."""
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # -11 = STD_OUTPUT_HANDLE, 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self(text, "1")

    def dim(self, text: str) -> str:
        return self(text, "2")

    def cyan(self, text: str) -> str:
        return self(text, "36;1")


def print_banner(style: Style, host: str, port: int, interval: float, show_qr: bool) -> str | None:
    """Print the startup banner. Returns the LAN URL, if there is one."""
    local_url = f"http://localhost:{port}"
    lan_ips = netinfo.all_lan_ips() if host in ("0.0.0.0", "::") else []
    lan_url = f"http://{lan_ips[0]}:{port}" if lan_ips else None

    print()
    print(style.bold(f"  Claude Code Usage Meter v{__version__}"))
    print(style.dim(f"  polling Anthropic every {interval:.0f}s"))
    print()
    print(f"  {style.dim('On this computer:')}  {style.cyan(local_url)}")

    if lan_url:
        print(f"  {style.dim('On your phone:')}     {style.cyan(lan_url)}")
        for extra in lan_ips[1:]:
            print(f"  {style.dim('  also:')}           {style.dim(f'http://{extra}:{port}')}")
        print()
        print(style.dim("  Phone must be on the same Wi-Fi network."))
    elif host in ("0.0.0.0", "::"):
        print(style.dim("  (No LAN address found - are you connected to a network?)"))
    else:
        print(style.dim(f"  Bound to {host} only; not reachable from your phone."))

    if lan_url and show_qr:
        if qr := netinfo.render_qr(lan_url):
            try:
                print()
                print(style.dim("  Scan to open on your phone:"))
                print()
                for line in qr.splitlines():
                    print("  " + line)
            except UnicodeEncodeError:
                # Console can't render the block characters; the URL above still works.
                print(style.dim("  (Console can't display the QR code - use the URL above.)"))

    print()
    print(style.dim("  Press Ctrl+C to stop."))
    print()
    return lan_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-meter",
        description="Serve a live Claude Code usage dashboard on your local network.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="bind address; use 127.0.0.1 to keep it off the network (default 0.0.0.0)",
    )
    parser.add_argument(
        "--interval", type=float, default=60.0, help="seconds between API polls (default 60)"
    )
    parser.add_argument("--no-qr", action="store_true", help="skip the QR code")
    parser.add_argument("--open", action="store_true", help="open the dashboard in your browser")
    parser.add_argument("--verbose", action="store_true", help="log every HTTP request")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # Two fixes in one call. line_buffering: otherwise the banner sits in a block
    # buffer whenever stdout isn't a console and never appears. utf-8: when output
    # is redirected, Windows falls back to the OEM codepage (cp850/cp437) and
    # mangles the QR code's block characters into mojibake.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    style = Style(_enable_ansi())

    poller = Poller(interval=args.interval)
    poller.start()

    try:
        server = make_server(args.host, args.port, poller, quiet=not args.verbose)
    except OSError as exc:
        print(f"\n  Could not bind {args.host}:{args.port} - {exc}", file=sys.stderr)
        print("  Try a different port, e.g. --port 8080\n", file=sys.stderr)
        poller.stop()
        return 1

    print_banner(style, args.host, args.port, args.interval, show_qr=not args.no_qr)

    if args.open:
        threading.Timer(0.5, webbrowser.open, [f"http://localhost:{args.port}"]).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(style.dim("  Shutting down."))
    finally:
        with contextlib.suppress(Exception):
            server.shutdown()
        poller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
