import { expect, it } from "vitest";
import { label, money, Claim } from "./api";
it("formats case status and currency", () => {
  expect(label("NEEDS_REVIEW")).toBe("Needs review");
  expect(money({ claim_amount: "4500.20", currency: "USD" } as Claim)).toBe(
    "$4,500.20",
  );
});
