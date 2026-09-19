import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Card } from ".";

describe("Card", () => {
  it("makes a clickable card keyboard-accessible without changing its content structure", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Card hoverable onClick={onClick}>
        <h3>Интервью</h3>
        <p>Практика ответов</p>
      </Card>,
    );

    const card = screen.getByRole("button", { name: /Интервью/ });
    await user.tab();
    expect(card).toHaveFocus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");

    expect(onClick).toHaveBeenCalledTimes(2);
  });
});
