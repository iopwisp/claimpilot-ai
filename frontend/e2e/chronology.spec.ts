import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

test("compare disputed dates against a notice receipt and export the cited result", async ({
  page,
}) => {
  const data = {
    email: randomUUID() + "@example.invalid",
    password: randomUUID(),
  };
  await page.request.post("/api/v1/auth/register", {
    data,
    failOnStatusCode: true,
  });
  await page.request.post("/api/v1/auth/login", {
    data,
    headers: { "X-ClaimPilot-Request": "browser" },
    failOnStatusCode: true,
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sample cases" }).click();
  await page.getByRole("radio", { name: /Disputed notice window/ }).check();
  await page.getByRole("button", { name: "Import sample" }).click();
  await page.getByRole("button", { name: "Analyze claim" }).click();
  await expect(
    page.getByRole("button", { name: "Export report" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Chronology", exact: true }).click();
  const timeline = page.getByRole("region", { name: "Case chronology" });
  await expect(timeline.getByText("8 days elapsed")).toBeVisible();
  await expect(timeline.getByText("7 days elapsed")).toBeVisible();
  await expect(timeline.getByText("Outside window")).toBeVisible();
  await expect(timeline.getByText("Within window")).toBeVisible();
  await timeline.getByLabel("Filter event type").selectOption("notice");
  await timeline
    .locator("ol")
    .getByRole("button", { name: /notice.pdf/ })
    .click();
  const source = page.getByRole("dialog", { name: "Source document" });
  await expect(source.locator("blockquote")).toHaveText(
    "Notice Date: 2026-05-11",
  );
  await expect(source.locator("img")).toBeVisible();
  await source.getByRole("button", { name: "Close source" }).click();
  const download = page.waitForEvent("download");
  await timeline.getByRole("button", { name: "Export comparison" }).click();
  const result = await readFile((await (await download).path())!, "utf8");
  for (const snippet of [
    "8 days · Outside window",
    "7 days · Within window",
    "police.pdf",
    "notice.pdf",
    "form.pdf",
    "calendar days",
  ])
    expect(result).toContain(snippet);
  await timeline.getByLabel("Filter event type").selectOption("");
  if (process.env.CAPTURE_CHRONOLOGY)
    await timeline.screenshot({ path: "../demo/media/chronology.png" });
  await timeline.getByLabel("Window in calendar days").fill("8");
  await expect(
    timeline.getByText("Within window", { exact: true }),
  ).toHaveCount(2);
  await timeline.getByRole("button", { name: "Test 7-day window" }).click();
  await expect(timeline.getByLabel("Window in calendar days")).toHaveValue("7");
  await expect(
    timeline.getByText("Outside window", { exact: true }),
  ).toBeVisible();
  await timeline.getByLabel("Window in calendar days").fill("");
  await expect(
    timeline.getByRole("button", { name: "Export comparison" }),
  ).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByText("View chronology from this run").click();
  await expect(timeline.getByText("Outside window")).toBeVisible();
});
