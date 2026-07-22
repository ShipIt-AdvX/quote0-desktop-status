from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mcstatus import JavaServer


@dataclass
class McStatus:
    online: bool
    host: str
    port: int
    motd: str
    version: str
    players_online: int
    players_max: int
    players: list[str]
    latency_ms: float | None
    error: str


def _mc_host_port() -> tuple[str, int]:
    from config import runtime_mc

    host, port = runtime_mc()
    host = (host or "frp-web.com").strip() or "frp-web.com"
    # allow host:port in mc_host
    if ":" in host and not host.startswith("["):
        h, _, p = host.rpartition(":")
        if p.isdigit():
            host, port = h, int(p)
    return host, port


def query_status(host: str | None = None, port: int | None = None, timeout: float = 5.0) -> McStatus:
    h, p = _mc_host_port()
    if host is not None:
        h = host
    if port is not None:
        p = port

    try:
        server = JavaServer(h, p, timeout=timeout)
        st = server.status()
        sample = st.players.sample or []
        names = [p.name for p in sample]
        if hasattr(st.motd, "to_plain"):
            motd = st.motd.to_plain()
        else:
            motd = str(getattr(st, "description", "") or "")
        motd = " ".join(motd.split())[:80]
        return McStatus(
            online=True,
            host=h,
            port=p,
            motd=motd,
            version=str(st.version.name)[:40],
            players_online=int(st.players.online),
            players_max=int(st.players.max),
            players=names,
            latency_ms=round(float(st.latency), 1),
            error="",
        )
    except Exception as e:
        return McStatus(
            online=False,
            host=h,
            port=p,
            motd="",
            version="",
            players_online=0,
            players_max=0,
            players=[],
            latency_ms=None,
            error=str(e)[:80],
        )


def mc_as_dict() -> dict[str, Any]:
    return asdict(query_status())
