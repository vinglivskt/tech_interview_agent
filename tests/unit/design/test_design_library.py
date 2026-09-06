"""DB-free тесты библиотеки тем системного дизайна (library.yaml) и генератора шагов."""

import pytest
from src.features.design.domain.scenarios import build_dynamic_steps, load_scenarios


@pytest.fixture
def scenarios(make_settings):
    return load_scenarios(make_settings())


def test_library_loads_full_topic_set(scenarios):
    assert len(scenarios) >= 100
    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids)), "Id сценариев не должны дублироваться"


def test_library_covers_all_categories(scenarios):
    categories = {s.category or "basics" for s in scenarios}
    for expected in (
        "basics",
        "read-heavy",
        "realtime",
        "queues",
        "distributed",
        "db",
        "kafka",
        "ecommerce",
        "search",
        "social",
        "geo",
        "api",
        "reliability",
        "consistency",
        "observability",
        "cdn",
        "security",
        "realworld",
        "pattern",
    ):
        assert expected in categories, f"Нет категории {expected}"


def test_library_levels_present(scenarios):
    levels = {s.level for s in scenarios}
    assert {"junior", "middle", "senior"} <= levels


def test_library_cards_have_rich_shape(scenarios):
    for scen in scenarios:
        assert scen.title
        assert scen.level in ("junior", "middle", "senior")
        assert isinstance(scen.summary, str)
        assert isinstance(scen.requirements, list)
        assert isinstance(scen.nfr, list)
        assert isinstance(scen.constraints, list)
        assert isinstance(scen.baseline_load, dict)
        assert isinstance(scen.acceptance_criteria, list)
        assert isinstance(scen.tags, list)


def test_detailed_yaml_overrides_library_card(scenarios):
    url_shortener = next(s for s in scenarios if s.id == "url-shortener")
    assert [st.id for st in url_shortener.steps] == [
        "clarify",
        "hla",
        "data",
        "scale",
        "api",
        "tradeoffs",
    ]
    assert url_shortener.level == "junior"


def test_dynamic_steps_basic_ladder_for_middle(make_settings):
    scenarios = load_scenarios(make_settings())
    scen = next(s for s in scenarios if s.id == "online-presence")
    assert scen.level == "middle"
    assert not scen.steps

    steps = build_dynamic_steps(scen)
    assert [st.id for st in steps] == ["clarify", "hla", "data", "scale", "tradeoffs", "failure"]


def test_dynamic_steps_include_evolution_level(make_settings):
    scenarios = load_scenarios(make_settings())
    scen = next(s for s in scenarios if s.id == "static-cdn")
    assert len(scen.evolution) >= 1

    steps = build_dynamic_steps(scen)
    assert [st.id for st in steps] == ["clarify", "evolve-1", "failure"]


def test_dynamic_steps_add_advanced_only_for_senior(make_settings):
    scenarios = load_scenarios(make_settings())
    senior = next(s for s in scenarios if s.id == "reddit-like")
    assert senior.level == "senior"

    steps = build_dynamic_steps(senior)
    assert [st.id for st in steps] == [
        "clarify", "hla", "data", "scale", "tradeoffs", "failure", "advanced",
    ]


def test_dynamic_steps_have_rubric_hint_and_points(make_settings):
    scenarios = load_scenarios(make_settings())
    scen = next(s for s in scenarios if s.id == "online-presence")
    first = build_dynamic_steps(scen)[0]
    assert first.id == "clarify"
    assert first.title == "Уточнение требований"
    assert first.rubric_weights
    assert first.expected_points
    assert first.hint
