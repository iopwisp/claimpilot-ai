import { expect, it } from "vitest";
import { compareDays } from "./Chronology";

it("uses calendar days across leap days and daylight saving changes", () => {
  expect(compareDays("2024-02-28", "2024-03-01", 1)).toEqual({
    days: 2,
    outcome: "Outside window",
  });
  expect(compareDays("2026-03-07", "2026-03-09", 2)).toEqual({
    days: 2,
    outcome: "Within window",
  });
  expect(compareDays("2026-05-11", "2026-05-11", 0)).toEqual({
    days: 0,
    outcome: "Within window",
  });
  expect(compareDays("2026-05-11", "2026-05-10", 7)).toEqual({
    days: -1,
    outcome: "Before incident",
  });
});
