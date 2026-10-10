import { expect, test } from "@playwright/test";
import { seed, signIn } from "./helpers";

const T21 = "Add what happens if the CRM is down: retry a few times, then put it in the analyst's queue.";

test.describe("Story refinement (M12)", () => {
  test.beforeEach(async ({ page, request }) => {
    await seed(request, "kyc_before_refinement");
    await signIn(page, request);
  });

  test("AC-M12-3: the T21 refinement previews, applies, and adds the edge case and the analyst queue", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_record_kyc");
    await expect(page.getByTestId("story-markdown")).not.toContainText("CRM unavailable");
    await page.getByLabel("Refine instruction").fill(T21);
    await page.getByRole("button", { name: "Preview change" }).click();
    const preview = page.getByTestId("refine-preview");
    await expect(preview).toContainText("new exception 'CRM unavailable'");
    await expect(preview).toContainText("New human queue 'CRM unavailable' in the Onboarding Analyst lane");
    await preview.getByRole("button", { name: "Apply" }).click();
    await expect(preview).toHaveCount(0);
    const story = page.getByTestId("story-markdown");
    await expect(story).toContainText("CRM unavailable (exc_crm_unavailable): manual review; notify Onboarding Analyst");
    await expect(story).toContainText("CRM outage retries, then goes to an analyst");
    await expect(page.getByTestId("history").locator("li").first()).toContainText("T21: refine story_record_kyc");

    await page.getByRole("link", { name: "Flow" }).click();
    const queue = page.getByTestId("flow-node-queue_exc_crm_unavailable");
    await expect(queue).toContainText("HUMAN QUEUE");
    await expect(queue).toContainText("CRM unavailable");
    await expect(queue).toContainText("Onboarding Analyst");
  });

  test("AC-M12-4: a split gives two stories with DoR, and undo restores the previous version", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_request_docs");
    await page.getByLabel("Refine instruction").fill("Split this into sending the request and handling replies");
    await page.getByRole("button", { name: "Preview change" }).click();
    const preview = page.getByTestId("refine-preview");
    await expect(preview).toContainText("After: story_request_docs");
    await expect(preview).toContainText("After: story_handle_replies");
    await expect(preview).toContainText("New connection node_handle_replies → node_verify_id");
    await preview.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByTestId("story-markdown")).toContainText("Send KYC document request");

    await page.getByRole("link", { name: "← All stories" }).click();
    const rows = page.getByTestId("stories-table").locator("tbody tr");
    await expect(rows).toHaveCount(10);
    const replies = rows.filter({ hasText: "Handle client replies" });
    await expect(replies).toContainText("DoR");
    await replies.getByRole("link").click();
    await expect(page.getByTestId("story-markdown")).toContainText("Uploaded documents are filed");

    await page.goto("/ideas/idea_client_kyc/stories/story_request_docs");
    const history = page.getByTestId("history");
    await expect(history.locator("li").first()).toContainText("refine story_request_docs");
    await history.locator("li").first().getByRole("button", { name: "Undo" }).click();
    await expect(page.getByTestId("story-markdown")).toContainText("Request KYC documents");
    await page.getByRole("link", { name: "← All stories" }).click();
    await expect(page.getByTestId("stories-table").locator("tbody tr")).toHaveCount(9);
  });

  test("merge: chasing folds into the request story, and undo brings it back", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_request_docs");
    await page.getByLabel("Refine instruction").fill("Merge this with chasing");
    await page.getByRole("button", { name: "Preview change" }).click();
    const preview = page.getByTestId("refine-preview");
    await expect(preview).toContainText("Merged 'Chase missing documents' into 'Request KYC documents'");
    await expect(preview).toContainText("Removed 'Chase missing documents'");
    await preview.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByTestId("story-markdown")).toContainText("Reminders follow the agreed schedule");

    await page.getByRole("link", { name: "← All stories" }).click();
    await expect(page.getByTestId("stories-table").locator("tbody tr")).toHaveCount(8);
    await expect(page.getByTestId("stories-table")).not.toContainText("Chase missing documents");

    await page.goto("/ideas/idea_client_kyc/stories/story_request_docs");
    await page.getByTestId("history").locator("li").first().getByRole("button", { name: "Undo" }).click();
    await page.getByRole("link", { name: "← All stories" }).click();
    await expect(page.getByTestId("stories-table").locator("tbody tr")).toHaveCount(9);
  });

  test("AC-M12-5: an instruction that reaches outside the story is rejected with an explanation", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_record_kyc");
    await page.getByLabel("Refine instruction").fill("Also rename the decline step to Reject client");
    await page.getByRole("button", { name: "Preview change" }).click();
    await expect(page.getByRole("alert")).toContainText("outside the story: Decline client (/nodes/node_decline/name)");
    await expect(page.getByTestId("refine-preview")).toHaveCount(0);
  });

  test("a question is answered without changing the story", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_record_kyc");
    await page.getByLabel("Refine instruction").fill("Who approves this?");
    await page.getByRole("button", { name: "Preview change" }).click();
    await expect(page.getByTestId("refine-answer")).toContainText("Nobody approves recording");
  });

  test("inline priority edit is a patch in the history", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_chase_docs");
    await page.getByLabel("Priority").selectOption("could");
    await expect(page.getByTestId("story-markdown")).toContainText("Could have");
    await expect(page.getByTestId("history").locator("li").first()).toContainText("Edited priority of Chase missing documents");
  });

  test("ask someone adds an open question to the story", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories/story_decline");
    await page.getByLabel("Question").fill("Must the decline letter be reviewed by legal?");
    await page.getByLabel("Who").selectOption("user_priya_shah");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Asked Priya Shah (MLRO)")).toBeVisible();
    await expect(page.getByTestId("story-markdown")).toContainText("Must the decline letter be reviewed by legal? (major, asked, waiting on sme_priya_shah)");
  });
});
