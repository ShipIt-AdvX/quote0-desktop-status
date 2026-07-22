from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CURSOR_PROJECTS


@dataclass
class AgentStatus:
    active: bool
    project: str
    title: str
    state: str
    last_update: str
    last_role: str
    snippet: str
    transcript_id: str


_USER_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
_TITLE_HINT = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _projects_root() -> Path:
    return CURSOR_PROJECTS


def _iter_transcripts() -> list[Path]:
    root = _projects_root()
    if not root.is_dir():
        return []
    files: list[Path] = []
    for p in root.glob("*/agent-transcripts/*.jsonl"):
        files.append(p)
    # Also nested uuid folders used by some Cursor builds
    for p in root.glob("*/agent-transcripts/*/*.jsonl"):
        files.append(p)
    return files


def _read_last_jsonl_records(path: Path, max_lines: int = 40) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in raw[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _extract_text(msg: dict[str, Any]) -> str:
    content = msg.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def _summarize(records: list[dict[str, Any]], path: Path) -> AgentStatus:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_sec = (datetime.now(timezone.utc) - mtime).total_seconds()
    # Consider "active" if transcript touched in last 3 minutes
    active = age_sec < 180

    project = path.parts[-3] if len(path.parts) >= 3 else path.parent.name
    # Prefer parent folder name under projects/
    try:
        idx = path.parts.index("projects")
        project = path.parts[idx + 1]
    except ValueError:
        pass

    title = "Cursor Agent"
    snippet = ""
    last_role = ""
    state = "idle"

    # Walk newest → oldest for last meaningful user query / assistant reply
    for rec in reversed(records):
        role = rec.get("role") or rec.get("message", {}).get("role") or ""
        text = _extract_text(rec) if "message" in rec else str(rec.get("content", ""))
        if not text and "message" in rec:
            text = _extract_text(rec)
        if not text:
            # Alternate schema: top-level type/message
            text = str(rec.get("text") or "")
        if not text:
            continue
        last_role = str(role or last_role)
        m = _USER_RE.search(text)
        if m:
            q = " ".join(m.group(1).split())
            title = q[:48] + ("…" if len(q) > 48 else "")
            snippet = q[:120]
            break
        if role in ("assistant", "user") or not title:
            flat = " ".join(text.split())
            if flat:
                snippet = flat[:120]
                if title == "Cursor Agent":
                    title = flat[:48] + ("…" if len(flat) > 48 else "")
                if role:
                    break

    # Infer busy vs idle from recency + last role
    if active:
        if last_role == "assistant":
            state = "working"
        elif last_role == "user":
            state = "working"
        else:
            state = "active"
    else:
        state = "idle"

    # Tool-call hint: look for recent function calls in last few records
    recent = records[-8:]
    blob = json.dumps(recent)
    if active and any(
        k in blob
        for k in (
            "tool_call",
            "toolCall",
            "functions.",
            "Shell",
            "Write",
            "StrReplace",
        )
    ):
        state = "working"

    return AgentStatus(
        active=active,
        project=project[:32],
        title=title,
        state=state,
        last_update=mtime.astimezone().strftime("%H:%M:%S"),
        last_role=str(last_role),
        snippet=snippet,
        transcript_id=path.stem[:8],
    )


def collect_agent() -> AgentStatus:
    files = _iter_transcripts()
    if not files:
        return AgentStatus(
            active=False,
            project="—",
            title="无 Agent 会话",
            state="idle",
            last_update="—",
            last_role="",
            snippet="未找到 agent-transcripts",
            transcript_id="",
        )

    newest = max(files, key=lambda p: p.stat().st_mtime)
    records = _read_last_jsonl_records(newest)
    return _summarize(records, newest)


def agent_as_dict() -> dict[str, Any]:
    return asdict(collect_agent())
