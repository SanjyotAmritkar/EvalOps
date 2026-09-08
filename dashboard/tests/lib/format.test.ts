import { describe, expect, it } from "vitest";
import {
  formatDateTime,
  formatFraction,
  formatRelativeTime,
  shortId,
} from "@/lib/format";

describe("formatDateTime", () => {
  it("renders a parseable ISO timestamp with the year present", () => {
    expect(formatDateTime("2026-09-08T12:30:00Z")).toContain("2026");
  });

  it("returns the raw input for an unparseable value", () => {
    expect(formatDateTime("not-a-date")).toBe("not-a-date");
  });
});

describe("formatRelativeTime", () => {
  const now = new Date("2026-09-08T12:00:00Z");

  it("describes an hour in the past", () => {
    const out = formatRelativeTime("2026-09-08T11:00:00Z", now);
    expect(out).toContain("hour");
    expect(out).toContain("ago");
  });

  it("describes seconds in the past", () => {
    const out = formatRelativeTime("2026-09-08T11:59:30Z", now);
    expect(out).toContain("second");
  });

  it("describes a time in the future", () => {
    const out = formatRelativeTime("2026-09-10T12:00:00Z", now);
    expect(out).toMatch(/in .*day/);
  });

  it("returns the raw input for an unparseable value", () => {
    expect(formatRelativeTime("nope", now)).toBe("nope");
  });
});

describe("formatFraction", () => {
  it("shows the fraction and its percentage", () => {
    expect(formatFraction(0.1)).toBe("0.1 (10%)");
    expect(formatFraction(0.2)).toBe("0.2 (20%)");
  });

  it("handles non-round percentages", () => {
    expect(formatFraction(0.155)).toBe("0.155 (15.5%)");
  });
});

describe("shortId", () => {
  it("truncates long ids with an ellipsis", () => {
    expect(shortId("0123456789abcdef")).toBe("01234567…");
  });

  it("leaves short ids alone", () => {
    expect(shortId("abc")).toBe("abc");
  });
});
