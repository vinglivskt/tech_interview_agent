"""Chunking utilities for RAG indexing."""

from __future__ import annotations

import re


def chunk_text(text: str, max_chunk_chars: int, overlap: int = 0) -> list[str]:
    if max_chunk_chars <= 0:
        raise ValueError("max_chunk_chars должен быть > 0")
    if overlap < 0:
        raise ValueError("overlap должен быть >= 0")
    if overlap >= max_chunk_chars:
        raise ValueError("overlap должен быть меньше max_chunk_chars")

    t = text.strip()
    if not t:
        return []

    raw_parts: list[str] = []
    for para in re.split(r"\n\s*\n+", t):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chunk_chars:
            raw_parts.append(para)
            continue
        start = 0
        while start < len(para):
            end = min(start + max_chunk_chars, len(para))
            piece = para[start:end].strip()
            if piece:
                raw_parts.append(piece)
            if end >= len(para):
                break
            start = end - overlap if overlap else end

    merged: list[str] = []
    cur = ""
    for p in raw_parts:
        if not cur:
            cur = p
        elif len(cur) + 2 + len(p) <= max_chunk_chars:
            cur = f"{cur}\n\n{p}"
        else:
            merged.append(cur)
            cur = p
    if cur:
        merged.append(cur)

    return merged if merged else [t[:max_chunk_chars]]
