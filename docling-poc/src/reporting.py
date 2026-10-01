"""Terminal reporting for the POC.

The experiment is only useful if you can see, for every element: which file it
came from, where in that file, which stage produced it, and what the actual
text is. This module is the single place that prints, so the pipeline modules
stay free of presentation concerns and the JSON output stays clean.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

# Windows consoles default to cp1252 and will raise on box-drawing characters.
# Reconfigure once, early, instead of letting a UnicodeEncodeError kill a run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable
        pass

RULE = "=" * 78
THIN = "-" * 78

# ANSI colours, disabled when the output is redirected or NO_COLOR is set.
_COLOUR = sys.stdout.isatty() and not os.getenv("NO_COLOR")


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


def bold(text: str) -> str:
    return _c(text, "1")


def dim(text: str) -> str:
    return _c(text, "2")


def green(text: str) -> str:
    return _c(text, "32")


def yellow(text: str) -> str:
    return _c(text, "33")


def red(text: str) -> str:
    return _c(text, "31")


def cyan(text: str) -> str:
    return _c(text, "36")


def rule(title: str = "") -> None:
    if title:
        print(f"\n{bold(RULE)}\n{bold(title)}\n{RULE}")
    else:
        print(RULE)


def step(number: str, title: str) -> None:
    print(f"\n{bold(cyan('=' * 78))}")
    print(f"{bold(cyan(f'STAGE {number}: {title}'))}")
    print(bold(cyan("=" * 78)))


def kv(label: str, value: Any, width: int = 26) -> None:
    print(f"  {label:<{width}} {value}")


def preview(text: str, limit: int = 220, indent: str = "      ") -> None:
    """Print extracted text, truncated but never silently."""
    flat = " ".join(str(text).split())
    if not flat:
        print(f"{indent}{dim('(empty)')}")
        return
    if len(flat) <= limit:
        print(f"{indent}{flat}")
        return
    print(f"{indent}{flat[:limit]}{dim(f' ... [+{len(flat) - limit} chars]')}")


def bullet(text: str) -> None:
    print(f"    - {text}")


def status(label: str, state: str, detail: str = "") -> None:
    """One consistent status line: OK / SKIP / FAIL."""
    colour = {"OK": green, "SKIP": yellow, "FAIL": red}.get(state, dim)
    suffix = f"  {dim(detail)}" if detail else ""
    print(f"  {colour(f'[{state:4s}]')} {label}{suffix}")


def element(
    *,
    index: int,
    content_type: str,
    producer: str,
    source: str,
    page: int | None,
    section: str,
    text: str,
    limit: int = 220,
    extra: Iterable[tuple[str, Any]] = (),
) -> None:
    """The main per-element report: where it came from and what it says."""
    where = f"page {page}" if page else "no page"
    print(
        f"\n  {bold(f'[{index:02d}]')} {bold(content_type.upper())} "
        f"{dim(f'(produced by {producer})')}"
    )
    print(f"      {dim('source:')} {source}")
    print(f"      {dim('where: ')} {where}   {dim('section:')} {section or '-'}")
    for key, value in extra:
        print(f"      {dim(key + ':')} {value}")
    print(f"      {dim('text:  ')}")
    preview(text, limit=limit)


def table(rows: list[list[str]], headers: list[str]) -> None:
    """Minimal fixed-width table; no third-party pretty-printer needed."""
    if not rows:
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    line = "  " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  " + "-+-".join("-" * w for w in widths))
    for row in rows:
        print("  " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
