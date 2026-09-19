import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { QuestionEntryContainer } from ".";
import { chatApi } from "@/services/api";

describe("QuestionEntryContainer", () => {
  it("сохраняет введённые вопрос и ответ через общий API сохранения", async () => {
    const user = userEvent.setup();
    const saveQA = vi.spyOn(chatApi, "saveQA").mockResolvedValue({ status: "saved", number: 42 });

    render(<QuestionEntryContainer onBack={vi.fn()} />);

    await user.type(screen.getByLabelText("Название вопроса"), "Что такое GIL?");
    await user.type(screen.getByLabelText("Ответ на вопрос"), "GIL ограничивает выполнение байткода.");
    await user.click(screen.getByRole("button", { name: "Сохранить в Word" }));

    expect(saveQA).toHaveBeenCalledWith("Что такое GIL?", "GIL ограничивает выполнение байткода.");
    expect(await screen.findByText("Вопрос сохранён в Word под №42")).toBeInTheDocument();
    expect(screen.getByLabelText("Название вопроса")).toHaveValue("");

    saveQA.mockRestore();
  });

  it("показывает, что дубликат не был добавлен", async () => {
    const user = userEvent.setup();
    const saveQA = vi.spyOn(chatApi, "saveQA").mockResolvedValue({ status: "skipped" });

    render(<QuestionEntryContainer onBack={vi.fn()} />);
    await user.type(screen.getByLabelText("Название вопроса"), "Что такое GIL?");
    await user.type(screen.getByLabelText("Ответ на вопрос"), "Ответ");
    await user.click(screen.getByRole("button", { name: "Сохранить в Word" }));

    expect(await screen.findByText("Такой вопрос уже есть в базе")).toBeInTheDocument();
    expect(screen.getByLabelText("Название вопроса")).toHaveValue("Что такое GIL?");

    saveQA.mockRestore();
  });
});
