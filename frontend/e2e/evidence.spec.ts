import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import path from "node:path";

test("reviewer requests evidence and handler supplies a processed document", async ({
  browser,
  baseURL,
}) => {
  const handler = await browser.newContext({ baseURL });
  const reviewer = await browser.newContext({ baseURL });
  const headers = { "X-ClaimPilot-Request": "browser" };
  try {
    const credentials = {
      email: randomUUID() + "@example.invalid",
      password: randomUUID(),
    };
    const reviewerEmail = process.env.E2E_REVIEWER_EMAIL!;
    await handler.request.post("/api/v1/auth/register", {
      data: credentials,
      failOnStatusCode: true,
    });
    await handler.request.post("/api/v1/auth/login", {
      data: credentials,
      headers,
      failOnStatusCode: true,
    });
    await reviewer.request.post("/api/v1/auth/login", {
      data: {
        email: reviewerEmail,
        password: process.env.E2E_REVIEWER_PASSWORD,
      },
      headers,
      failOnStatusCode: true,
    });
    const claim = await (
      await handler.request.post("/api/v1/samples", {
        headers,
        data: { scenario: "03-missing-evidence", request_id: randomUUID() },
        failOnStatusCode: true,
      })
    ).json();
    await handler.request.patch("/api/v1/claims/" + claim.id, {
      headers,
      data: { reviewer_email: reviewerEmail },
      failOnStatusCode: true,
    });
    const owner = await handler.newPage();
    await owner.goto("/");
    await owner
      .getByRole("button", { name: claim.claim_number, exact: true })
      .click();
    await owner.getByRole("button", { name: "Analyze claim" }).click();
    await expect(
      owner.getByText("Request damage evidence.", { exact: true }),
    ).toBeVisible();
    const checker = await reviewer.newPage();
    await checker.goto("/");
    await checker
      .getByRole("button", { name: claim.claim_number, exact: true })
      .click();
    await checker
      .getByRole("button", { name: "Review report", exact: true })
      .click();
    await checker.getByRole("button", { name: "Request material" }).click();
    await expect(
      checker.getByRole("heading", { name: "Evidence requests" }),
    ).toBeVisible();
    await owner.getByRole("button", { name: "Documents", exact: true }).click();
    await owner
      .getByLabel("Upload files")
      .setInputFiles(
        path.resolve("../demo/03-missing-evidence/follow-up/invoice.pdf"),
      );
    await owner
      .getByRole("combobox", { name: "Document for Damage evidence" })
      .selectOption({ label: "invoice.pdf" });
    await owner.getByRole("button", { name: "Submit document" }).click();
    await checker.getByRole("button", { name: "Accept evidence" }).click();
    await expect(checker.getByText("Accepted", { exact: true })).toBeVisible();
    await owner.getByRole("button", { name: "Analyze claim" }).click();
    await expect(
      owner.getByRole("button", { name: "Export report" }),
    ).toBeVisible();
    await checker
      .getByRole("button", { name: "Review report", exact: true })
      .click();
    await checker.getByRole("button", { name: "Complete review" }).click();
    await expect(checker.locator(".heading .badge")).toHaveText("Completed");
  } finally {
    await handler.close();
    await reviewer.close();
  }
});
