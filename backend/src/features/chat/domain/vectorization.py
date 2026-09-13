"""Утилиты для разбиения текста на чанки для индексации RAG."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(text: str, max_chunk_chars: int, overlap: int = 0) -> list[str]:
    """
    Разбивает текст на чанки заданной длины с перекрытием.

    Сценарий 3 LangChain-интеграции: нарезка делегируется
    ``RecursiveCharacterTextSplitter`` (сепараторы абзац/строка/предложение),
    затем применяется та же «склейка» коротких кусков до максимума, что и в
    оригинальной реализации. Контракт и сигнатура не меняются.
    :param text: исходный текст
    :param max_chunk_chars: максимальная длина чанка
    :param overlap: перекрытие между чанками
    :return: список чанков
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

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_chars,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " "],
    )
    parts = [p.strip() for p in splitter.split_text(t) if p.strip()]

    merged: list[str] = []
    cur = ""
    for p in parts:
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