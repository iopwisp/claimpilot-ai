import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import {randomUUID} from "node:crypto";
test("handler submits evidence and assigned reviewer reconciles dates", async ({
  page,
}) => {
  const tag = Date.now(),
    email = "handler-" + tag + "@example.invalid",
    password = randomUUID();
  const demo = path.resolve("../demo/02-date-mismatch");
  const claim = JSON.parse(
    fs.readFileSync(path.join(demo, "claim.json"), "utf8"),
  );
  await page.goto("/");
  await page.getByText("Create an account", { exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByRole("button", { name: "New claim" }).click();
  const form = page.getByRole("dialog");
  for (const [label, key] of Object.entries({
    "Claimant name": "claimant_name",
    "Policy number": "policy_number",
    "Incident date": "incident_date",
    "Claim amount": "claim_amount",
    "Incident description": "incident_description",
  })) {
    await form.getByLabel(label).fill(claim[key]);
  }
  await form.getByRole("button", { name: "Create claim" }).click();
  await page.getByLabel("Upload files").setInputFiles(
    fs
      .readdirSync(demo)
      .filter((n) => n.endsWith(".pdf"))
      .map((n) => path.join(demo, n)),
  );
  const reviewer = process.env.E2E_REVIEWER_EMAIL!,
    secret = process.env.E2E_REVIEWER_PASSWORD!;
  await page.getByPlaceholder("Reviewer email").fill(reviewer);
  await page.getByRole("button", { name: "Assign reviewer" }).click();
  await page.getByRole("button", { name: "Analyze claim" }).click();
  await expect(page.getByText("Date mismatch", { exact: true })).toBeVisible({
    timeout: 60000,
  });
  if (process.env.CAPTURE_DEMO) {
    fs.mkdirSync("../demo/media", { recursive: true });
    await page.screenshot({
      path: "../demo/media/date-mismatch.png",
      fullPage: true,
    });
  }
  const id = await page.locator(".eyebrow").innerText();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Email address").fill(reviewer);
  await page.getByLabel("Password", { exact: true }).fill(secret);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page
    .getByRole("button", { name: id.split(" · ")[0], exact: true })
    .click();
  await page
    .getByRole("button", { name: "Extracted data", exact: true })
    .click();
  const field = page
    .locator(".field")
    .filter({ has: page.getByRole("button", { name: /police.pdf/ }) })
    .filter({ has: page.getByLabel("Correct incident_date") });
  await field.getByLabel("Correct incident_date").fill(claim.incident_date);
  await field.getByRole("button",{name:/police.pdf/}).click();
  const viewer=page.getByRole("dialog",{name:"Source document"});
  await expect(viewer.locator("blockquote")).toContainText("Incident Date");
  await expect(viewer.locator("img")).toBeVisible();
  await viewer.getByRole("button",{name:"Close source"}).click();
  await field.getByRole("button", { name: "Save correction" }).click();
  await expect(field.getByText(/· Corrected/)).toBeVisible();
  await page
    .getByRole("button", { name: "Review report", exact: true })
    .click();
  await page.getByRole("button", { name: "Complete review" }).click();
  await expect(page.locator(".heading .badge")).toHaveText("Completed");
  await page.getByRole("button", { name: "Back to overview" }).click();
  await expect(page.locator("tbody").getByText("Completed",{exact:true})).toBeVisible();
  if (process.env.CAPTURE_DEMO)
    await page.screenshot({
      path: "../demo/media/workspace.png",
      fullPage: true,
    });
});
