"""Утилиты чанкинга и векторизации текста для RAG-индексации."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI


def chunk_text(text: str, max_chunk_chars: int, overlap: int = 0) -> list[str]:
    """
    Делит текст на фрагменты для последующей векторизации.

    Алгоритм:

    1. Разбивка по двойным переводам строк (абзацы).
    2. Длинные абзацы режутся окнами длины ``max_chunk_chars``; при ``overlap > 0`` окна перекрываются.
    3. Короткие абзацы склеиваются, пока не превышен ``max_chunk_chars``.

    Args:
        text: Исходный текст (например документ погоды).
        max_chunk_chars: Максимальная длина одного фрагмента в символах.
        overlap: Символов перекрытия между соседними окнами внутри одного длинного абзаца.

    Returns:
        Непустой список фрагментов; для пустой строки — ``[]``.
    """
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


async def vectorize_texts(
    openai: "AsyncOpenAI",
    model: str,
    texts: list[str],
    *,
    batch_size: int = 16,
) -> list[list[float]]:
    """Строит эмбеддинги OpenAI для списка текстов пакетами."""
    if not texts:
        return []
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = await openai.embeddings.create(model=model, input=batch)
        ordered = sorted(resp.data, key=lambda d: d.index)
        all_embeddings.extend(d.embedding for d in ordered)
    return all_embeddings
