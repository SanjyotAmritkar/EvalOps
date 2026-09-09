import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WorkflowSteps } from "@/components/ui/workflow-steps";

describe("WorkflowSteps", () => {
  it("renders each step label in order", () => {
    render(
      <WorkflowSteps
        steps={[
          { label: "Evaluation data" },
          { label: "Baseline" },
          { label: "Candidate", tone: "candidate" },
          { label: "Release decision" },
        ]}
      />,
    );
    const labels = screen
      .getAllByRole("listitem")
      .map((node) => node.textContent);
    expect(labels).toEqual([
      "Evaluation data",
      "Baseline",
      "Candidate",
      "Release decision",
    ]);
  });
});
