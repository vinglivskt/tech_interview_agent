import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DesignSetupView } from "./presentation";
import styles from "./design.module.css";

const CONFIG = {
  levels: ["junior", "middle", "senior"],
  scenarios: [
    {
      id: "url-shortener",
      title: "URL Shortener",
      level: "middle",
      summary: "Короткие ссылки, редиректы и подсчёт переходов.",
    },
    {
      id: "online-presence",
      title: "Online Presence",
      level: "middle",
      summary: "Онлайн/офлайн статусы друзей через heartbeat и TTL.",
    },
  ],
  hint_penalty_percent: 10,
};

function renderSetup(overrides?: {
  level?: string;
  selectedScenarioId?: string;
  scenarios?: typeof CONFIG.scenarios;
}) {
  const onLevelChange = vi.fn();
  const onScenarioSelect = vi.fn();
  const onStart = vi.fn();

  render(
    <DesignSetupView
      config={{ ...CONFIG, scenarios: overrides?.scenarios ?? CONFIG.scenarios }}
      level={overrides?.level ?? "middle"}
      selectedScenarioId={overrides?.selectedScenarioId ?? ""}
      onLevelChange={onLevelChange}
      onScenarioSelect={onScenarioSelect}
      onStart={onStart}
      onBack={vi.fn()}
      isLoading={false}
      error={null}
    />,
  );

  return { onLevelChange, onScenarioSelect, onStart };
}

describe("DesignSetupView: выбор сценария с кратким описанием", () => {
  const scenarioList = () => screen.getByTestId("design-scenario-list");

  it("показывает у каждого сценария заголовок и описание", () => {
    renderSetup();

    for (const scen of CONFIG.scenarios) {
      const card = within(scenarioList()).getByRole("button", { name: new RegExp(scen.title) });
      expect(card).not.toBeNull();
      expect(card.textContent).toContain(scen.title);
      expect(card.textContent).toContain(scen.summary);
    }
  });

  it("выводит карточку «Любой подходящий» для автовыбора", () => {
    renderSetup();

    const autoCard = within(scenarioList()).getByRole("button", { name: /Любой подходящий/ });
    expect(autoCard.textContent).toContain("Автоматический выбор");
    expect(autoCard.className).toContain(styles.selected);
  });

  it("фильтрует сценарии по выбранному уровню", () => {
    const mixedScenarios = [
      { ...CONFIG.scenarios[0], level: "junior" },
      { ...CONFIG.scenarios[1], level: "middle" },
    ];
    renderSetup({ level: "middle", scenarios: mixedScenarios });

    expect(within(scenarioList()).getByRole("button", { name: /Online Presence/ })).not.toBeNull();
    expect(within(scenarioList()).queryByRole("button", { name: /URL Shortener/ })).toBeNull();
  });

  it("выбор сценария вызывает onScenarioSelect с его id", async () => {
    const user = userEvent.setup();
    const { onScenarioSelect } = renderSetup();

    await user.click(within(scenarioList()).getByRole("button", { name: /URL Shortener/ }));
    expect(onScenarioSelect).toHaveBeenCalledWith("url-shortener");
  });

  it("выбранная карточка подсвечивается классом selected", () => {
    renderSetup({ selectedScenarioId: "url-shortener" });

    const card = within(scenarioList()).getByRole("button", { name: /URL Shortener/ });
    expect(card.className).toContain(styles.selected);
  });

  it("повторный клик по выбранной карточке сбрасывает выбор", async () => {
    const user = userEvent.setup();
    const { onScenarioSelect } = renderSetup({ selectedScenarioId: "url-shortener" });

    await user.click(within(scenarioList()).getByRole("button", { name: /URL Shortener/ }));
    expect(onScenarioSelect).toHaveBeenCalledWith("");
  });

  it("карточка «Любой подходящий» сбрасывает выбранный сценарий", async () => {
    const user = userEvent.setup();
    const { onScenarioSelect } = renderSetup({ selectedScenarioId: "online-presence" });

    await user.click(within(scenarioList()).getByRole("button", { name: /Любой подходящий/ }));
    expect(onScenarioSelect).toHaveBeenCalledWith("");
  });

  it("без сценариев для уровня показывает заглушку", () => {
    renderSetup({ scenarios: [] });

    expect(screen.getByText(/Сценариев для этого уровня пока нет/)).not.toBeNull();
  });

  it("сначала рендерится «Любой подходящий», затем сценарии", () => {
    renderSetup();

    const cards = within(scenarioList()).getAllByRole("button");
    expect(cards[0].textContent).toContain("Любой подходящий");
    expect(cards[1].textContent).toContain("URL Shortener");
    expect(cards[2].textContent).toContain("Online Presence");
  });
});