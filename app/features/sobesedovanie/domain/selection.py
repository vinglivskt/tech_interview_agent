from __future__ import annotations

import math
import uuid
from random import Random
from typing import Iterable

from .classification import ClassifiedQA
from .models import SobesQuestion


def _plan_count_by_level(level: str, counts_cfg: dict[str, list[int]]) -> int:
    lo, hi = counts_cfg.get(level, [18, 22])
    # детерминированный выбор середины
    return int(math.floor((lo + hi) / 2))


def _round_robin(groups: dict[str, list[ClassifiedQA]]) -> Iterable[ClassifiedQA]:
    buckets = {k: list(v) for k, v in groups.items() if v}
    keys = list(buckets.keys())
    i = 0
    while any(buckets.values()):
        key = keys[i % len(keys)]
        if buckets[key]:
            yield buckets[key].pop(0)
        i += 1


def select_questions(
    items: list[ClassifiedQA],
    *,
    level: str,
    topics: list[str],
    counts_cfg: dict[str, list[int]],
) -> tuple[list[SobesQuestion], int]:
    """
    Фильтрует по уровню, раскладывает по темам, сортирует по сложности (возрастание),
    чередует темы и набирает плановое количество вопросов.
    Возвращает (выбранные вопросы, total_planned).
    """
    if not items:
        return [], 0

    planned = _plan_count_by_level(level, counts_cfg)

    # 1) первичная фильтрация по уровню с допуском соседнего уровня при нехватке
    primary = [it for it in items if it.level == level]
    if len(primary) < planned:
        neighbors = {"junior": "middle", "middle": "junior", "senior": "middle"}
        primary += [it for it in items if it.level == neighbors.get(level, "middle") and it not in primary]

    # 2) сгруппировать по темам и отсортировать по сложности
    grouped: dict[str, list[ClassifiedQA]] = {}
    for it in primary:
        t = it.topic if it.topic in topics else "other"
        grouped.setdefault(t, []).append(it)
    for ts in grouped.values():
        ts.sort(key=lambda x: x.difficulty_score)

    # 3) раунд-робин по темам
    ordered: list[ClassifiedQA] = list(_round_robin(grouped))

    # 4) добор, если мало тем
    if len(ordered) < planned:
        rest = [it for it in items if it not in ordered]
        rest.sort(key=lambda x: x.difficulty_score)
        ordered.extend(rest)

    ordered = ordered[:planned]

    # 5) маппинг в SobesQuestion
    rng = Random(42)
    out: list[SobesQuestion] = []
    for it in ordered:
        out.append(
            SobesQuestion(
                id=f"s_{it.number}_{uuid.uuid4().hex[:8]}",
                number=it.number,
                text=it.question,
                topic=it.topic if it.topic in topics else "other",
                level=it.level,
                difficulty_score=float(it.difficulty_score),
            )
        )
    rng.shuffle(out)
    return out, planned
