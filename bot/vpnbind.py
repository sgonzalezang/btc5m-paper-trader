"""Pin this process's outbound sockets to the ExpressVPN tunnel.

Every outbound AF_INET socket is bound to the tunnel adapter's source address
before it connects, so traffic from this process leaves through the VPN no
matter what the system default route is or how the VPN client's per-app
split-tunnel rules are configured. App-based split tunnelling cannot separate
the trading scripts from each other (they all run as the same python.exe), so
the decision is made here instead.

If the tunnel is down there is no address to bind to, and the connection is
allowed out over the physical NIC rather than being blocked: a missed signal
costs more than the leak does, and the operator alerts on the failure anyway.
Set BTC5M_VPN_REQUIRE=1 to fail closed (raise VPNDown) instead.

Scope: sockets opened by *this* process. Subprocesses (notably git, used by
btc5m_bot's --publish) are unaffected and still need a split-tunnel rule.
Hostname lookups go through the OS resolver and are not covered either.
"""

import ipaddress
import os
import socket

# ExpressVPN's OpenVPN tunnel hands out RFC 6598 shared address space.
TUNNEL_NET = ipaddress.ip_network(os.environ.get("BTC5M_VPN_NET", "100.64.0.0/10"))

# Fail open by default: if the tunnel is down, let the signal out and alert on it.
REQUIRE_TUNNEL = os.environ.get("BTC5M_VPN_REQUIRE", "0").lower() in ("1", "true", "yes")


class VPNDown(RuntimeError):
    """Raised when an outbound connection is attempted with no tunnel to bind to."""


def tunnel_ip():
    """Return this host's address on the VPN tunnel, or None if it is not up."""
    override = os.environ.get("BTC5M_VPN_IP")
    if override:
        return override
    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return None
    for addr in candidates:
        try:
            if ipaddress.ip_address(addr) in TUNNEL_NET:
                return addr
        except ValueError:
            continue
    return None


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _is_loopback(target):
    try:
        return ipaddress.ip_address(target[0]).is_loopback
    except (ValueError, IndexError, TypeError):
        return False  # a hostname still gets pinned to the tunnel


def _pin_to_tunnel(sock, target):
    if sock.family != socket.AF_INET or _is_loopback(target):
        return
    try:
        if sock.getsockname()[0] != "0.0.0.0":
            return  # caller bound it already; leave their choice alone
    except OSError:
        pass

    source = tunnel_ip()
    if source is None:
        if REQUIRE_TUNNEL:
            raise VPNDown(
                "ExpressVPN tunnel is down (no %s address on this host); refusing to "
                "send %r over the clear interface" % (TUNNEL_NET, target)
            )
        return
    try:
        sock.bind((source, 0))
    except OSError as exc:
        raise VPNDown("could not bind outbound socket to tunnel %s: %s" % (source, exc)) from exc


def _connect(self, target):
    _pin_to_tunnel(self, target)
    return _real_connect(self, target)


def _connect_ex(self, target):
    _pin_to_tunnel(self, target)
    return _real_connect_ex(self, target)


def _install_proactor_hook():
    """Cover asyncio's Windows IOCP path, which aiohttp (and so discord.py) uses.

    ConnectEx() never goes through socket.connect(), so the hooks above never
    fire for it. asyncio instead calls _overlapped.BindLocal(), which binds the
    socket to INADDR_ANY and lets it take the default route -- straight out the
    clear NIC. Bind it to the tunnel instead.
    """
    try:
        import _overlapped
    except ImportError:
        return  # not Windows, or no proactor loop available

    real_bind_local = _overlapped.BindLocal

    def bind_local(fileno, family):
        source = tunnel_ip() if family == socket.AF_INET else None
        if source is None:
            if family == socket.AF_INET and REQUIRE_TUNNEL:
                raise VPNDown("ExpressVPN tunnel is down; refusing to bind an asyncio socket")
            return real_bind_local(fileno, family)
        # Wrap the raw handle to bind it, then detach so closing the wrapper
        # does not close the socket asyncio is about to hand to ConnectEx.
        sock = socket.socket(family, socket.SOCK_STREAM, fileno=fileno)
        try:
            sock.bind((source, 0))
        finally:
            sock.detach()

    _overlapped.BindLocal = bind_local


def install():
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    _install_proactor_hook()


install()
