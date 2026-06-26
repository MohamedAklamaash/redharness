"""A fetch-and-verify-by-hash dataset loader, gated behind explicit opt-in.

Real benchmark behavior sets (AdvBench, HarmBench, JBB-Behaviors, StrongREJECT)
are not committed to the repo; they are fetched from their canonical source and
verified by content hash, mirroring HarmBench/JBB practice (plan §4). This loader
implements that logic fully but never runs in the offline slice: it refuses to
fetch unless ``allow_download=True``, and supports ``file://`` URLs (also behind
the opt-in) so the hash-mismatch path is testable without a network.

Fetching is hardened against SSRF and resource exhaustion: only ``https`` and
``file`` schemes are permitted, http(s) hosts that resolve to private/loopback/
link-local ranges are blocked (cloud-metadata / internal-service protection), and
the response body is capped to a sane limit.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
from urllib.parse import urlparse
from urllib.request import urlopen

from redharness.core.dataset import Dataset
from redharness.core.models import Behavior
from redharness.core.registry import register_dataset
from redharness.datasets.loader import parse_behaviors, short_version, verify_hash
from redharness.errors import DatasetError

_ALLOWED_SCHEMES = {"https", "file"}
_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB cap to avoid memory exhaustion.


def _ssl_context() -> ssl.SSLContext:
    """Build a default-verifying SSL context backed by ``certifi`` when available.

    The python.org macOS build ships without a wired-up CA bundle, so the system
    default context fails verification with ``CERTIFICATE_VERIFY_FAILED`` against
    https sources. When ``certifi`` is importable (it ships with the
    openai/anthropic/dashboard extras) its bundled CA file is used; otherwise the
    plain default context is returned. ``certifi`` is never a hard core dependency —
    it is used only if present.
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _is_blocked_address(ip: str) -> bool:
    """True if ``ip`` is private, loopback, link-local, or otherwise non-public."""
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _assert_public_host(host: str) -> None:
    """Resolve ``host`` and refuse if any address is in a non-public range (SSRF)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise DatasetError(f"could not resolve host {host!r}: {exc}") from exc
    for info in infos:
        ip = str(info[4][0])
        if _is_blocked_address(ip):
            raise DatasetError(
                f"refusing to fetch from host {host!r}: resolves to non-public "
                f"address {ip} (SSRF protection)"
            )


class RemoteDataset(Dataset):
    """Downloads a behavior set from ``url`` and verifies it against ``sha256``."""

    name = "remote"

    def __init__(
        self,
        name: str,
        url: str,
        sha256: str,
        allow_download: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.url = url
        self.sha256 = sha256
        self.allow_download = allow_download
        self.timeout = timeout

    @property
    def version(self) -> str:
        return short_version(self.name, self.sha256)

    def _fetch(self) -> bytes:
        parsed = urlparse(self.url)
        scheme = parsed.scheme
        if scheme not in _ALLOWED_SCHEMES:
            raise DatasetError(
                f"refusing to fetch {self.name!r}: scheme {scheme!r} not allowed "
                f"(permitted: {', '.join(sorted(_ALLOWED_SCHEMES))})"
            )
        if not self.allow_download:
            raise DatasetError(
                f"refusing to fetch {self.name!r} from {self.url!r}: "
                "set allow_download=True to enable fetches"
            )
        if scheme == "https":
            host = parsed.hostname
            if not host:
                raise DatasetError(f"url {self.url!r} has no host")
            _assert_public_host(host)
        # Scheme is allow-listed to https/file above, so urlopen is constrained.
        # A certifi-backed SSL context is supplied for https so verification works
        # out of the box on macOS python.org builds; file:// ignores it.
        context = _ssl_context() if scheme == "https" else None
        with urlopen(self.url, timeout=self.timeout, context=context) as response:
            data = response.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise DatasetError(
                f"remote dataset {self.name!r} exceeds size cap of {_MAX_BYTES} bytes"
            )
        return data

    def load(self) -> list[Behavior]:
        data = self._fetch()
        verify_hash(data, self.sha256)
        behaviors = parse_behaviors(data)
        if not behaviors:
            raise DatasetError(f"remote dataset {self.name!r} is empty")
        return behaviors


# Register under the documented "remote" name so configs can reference it; it
# stays inert offline because every fetch path requires allow_download=True.
register_dataset("remote")(RemoteDataset)
