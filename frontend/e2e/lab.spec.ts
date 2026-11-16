import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";

test("simulate source loss, inspect the quote and restore a minimal packet", async ({
  page,
}) => {
  const data = {
    email: randomUUID() + "@example.invalid",
    password: randomUUID(),
  };
  const headers = { "X-ClaimPilot-Request": "browser" };
  const api = page.request;
  await api.post("/api/v1/auth/register", { data, failOnStatusCode: true });
  await api.post("/api/v1/auth/login", {
    data,
    headers,
    failOnStatusCode: true,
  });
  const claim = await (
    await api.post("/api/v1/samples", {
      data: { scenario: "01-complete", request_id: randomUUID() },
      headers,
      failOnStatusCode: true,
    })
  ).json();
  await page.goto("/");
  await page
    .getByRole("button", { name: claim.claim_number, exact: true })
    .click();
  await page.getByRole("button", { name: "Analyze claim" }).click();
  await expect(
    page.getByRole("button", { name: "Export report" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Evidence Lab", exact: true }).click();
  const lab = page.getByRole("region", { name: "Evidence Lab" });
  const include = (name: string) =>
    lab.getByRole("checkbox", { name: "Include " + name });
  const legend = lab.locator(".labLegend");
  await expect(legend).toContainText("7 intact");
  await include("form.pdf").uncheck();
  await include("invoice.pdf").uncheck();
  await include("policy.pdf").uncheck();
  await expect(legend).toContainText("5 lost");
  await lab.getByRole("button", { name: "Lost 5" }).click();
  const policy = lab
    .locator(".labItem")
    .filter({ has: page.getByText("Policy passage", { exact: true }) });
  await policy.locator("summary").click();
  await policy.getByRole("button", { name: /policy.pdf/ }).click();
  const viewer = page.getByRole("dialog", { name: "Source document" });
  await expect(viewer.locator("blockquote")).toContainText(
    "subject to inspection",
  );
  await expect(viewer.locator("img")).toBeVisible();
  await viewer.getByRole("button", { name: "Close source" }).click();
  await lab.getByRole("button", { name: "Find files to restore" }).click();
  await expect(lab.getByText("Fewest files to restore · 2")).toBeVisible();
  await lab.getByRole("button", { name: "Restore suggested files" }).click();
  await expect(legend).toContainText("0 lost");
  await expect(include("invoice.pdf")).not.toBeChecked();
  await lab.getByRole("button", { name: "Try this packet" }).click();
  await expect(lab.getByRole("checkbox", { checked: true })).toHaveCount(2);
  await expect(legend).toContainText("0 lost");
  await lab.getByText("Why these files?").click();
  await expect(
    lab.locator(".labPacket li").filter({ hasText: "1200 USD" }),
  ).toBeVisible();
  await lab.getByText("Why these files?").click();
  if (process.env.CAPTURE_LAB)
    await page.screenshot({
      path: "../demo/media/evidence-lab.png",
      fullPage: true,
    });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
  await lab.getByRole("button", { name: "Reset" }).click();
  await expect(legend).toContainText("7 intact");
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page
    .getByRole("button", { name: "Explore this run in Evidence Lab" })
    .click();
  await expect(legend).toContainText("7 intact");
});
