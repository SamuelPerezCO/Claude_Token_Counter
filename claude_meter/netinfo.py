"""LAN address discovery and terminal QR rendering for the console banner."""

from __future__ import annotations

import socket


def primary_lan_ip() -> str | None:
    """Best-guess LAN IP: the source address the OS would use to reach the internet.

    Opening a UDP socket sends no packets -- it just asks the routing table which
    interface would be used, which is exactly the address a phone on the same
    network needs.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def all_lan_ips() -> list[str]:
    """Every non-loopback IPv4 address on this host, primary first."""
    found: list[str] = []
    if primary := primary_lan_ip():
        found.append(primary)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127.") and address not in found:
                found.append(address)
    except OSError:
        pass
    return found


def render_qr(data: str) -> str | None:
    """Render `data` as an ASCII QR code, or None if the qrcode lib is absent."""
    try:
        import io

        import qrcode
    except ImportError:
        return None

    code = qrcode.QRCode(border=1)
    code.add_data(data)
    code.make(fit=True)
    buffer = io.StringIO()
    code.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()
