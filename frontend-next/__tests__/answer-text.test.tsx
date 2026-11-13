import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerText } from "@/components/dashboard/practice/answer-text";

describe("AnswerText", () => {
  it("renders bullet lines as a list and **text** as bold", () => {
    const { container } = render(
      <AnswerText text={"Case Intel has **3 hearings**.\n- Rao vs State\n- Sita vs Ram\n\nA second paragraph."} />,
    );
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Rao vs State", "Sita vs Ram"]);
    expect(container.querySelector("strong")?.textContent).toBe("3 hearings");
    expect(screen.getByText("A second paragraph.")).toBeInTheDocument();
  });

  it("never interprets HTML", () => {
    const { container } = render(<AnswerText text={"<img src=x onerror=alert(1)> **<b>x</b>**"} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
