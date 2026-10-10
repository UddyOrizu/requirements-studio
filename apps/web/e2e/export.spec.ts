import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { seed, signIn } from "./helpers";

const SAMPLE_JIRA = readFileSync(new URL("../../../samples/client_kyc/exports/jira_import.csv", import.meta.url), "utf8");

test.describe("Export screen (M9)", () => {
  test.beforeEach(async ({ page, request }) => {
    await seed(request, "samples");
    await signIn(page, request);
  });

  test("defaults, preview, single-file download equal to the sample, zip, and history", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/export");
    await expect(page.getByTestId("draft-banner")).toHaveCount(0);
    for (const label of ["Lucidchart (.drawio)", "Markdown (stories, improvements)", "Jira CSV"]) {
      await expect(page.getByLabel(label)).toBeChecked();
    }
    await expect(page.getByLabel("Azure DevOps CSV")).not.toBeChecked();
    await expect(page.getByTestId("export-preview")).toContainText("User stories — Client KYC checks");

    // Only Jira: a single file, byte-identical to samples/client_kyc/exports/jira_import.csv
    await page.getByLabel("Lucidchart (.drawio)").uncheck();
    await page.getByLabel("Markdown (stories, improvements)").uncheck();
    await page.getByRole("listitem").filter({ hasText: "Jira CSV" }).getByRole("button", { name: "Preview" }).click();
    await expect(page.getByTestId("export-preview")).toContainText("Issue ID,Issue Type,Summary,Parent");
    const single = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download file" }).click();
    const file = await single;
    expect(file.suggestedFilename()).toBe("jira_import.csv");
    expect(readFileSync(await file.path(), "utf8")).toBe(SAMPLE_JIRA);

    // Several formats: one zip
    await page.getByLabel("Azure DevOps CSV").check();
    await page.getByLabel("Excel workbook").check();
    const zip = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download 3 files (zip)" }).click();
    expect((await zip).suggestedFilename()).toBe("idea_client_kyc_v12_export.zip");

    const rows = page.getByTestId("export-history").locator("tbody tr");
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText("jira, ado, excel");
    await expect(rows.nth(1)).toContainText("superseded");
  });

  test("a not-ready idea shows the draft banner", async ({ page }) => {
    await page.goto("/ideas/idea_client_onboarding/export");
    await expect(page.getByTestId("draft-banner")).toContainText("Draft — 9 stories not ready.");
    await expect(page.getByTestId("export-preview")).toContainText("Draft — 9 stories not ready.");
  });
});
