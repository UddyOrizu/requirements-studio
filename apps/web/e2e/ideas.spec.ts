import { expect, test } from "@playwright/test";
import { seed, signIn } from "./helpers";

test.describe("Ideas workspace (M12)", () => {
  test.beforeEach(async ({ page, request }) => {
    await seed(request, "samples");
    await signIn(page, request);
  });

  test("AC-M12-1: the ideas list shows both sample ideas with their stats", async ({ page }) => {
    await page.goto("/");
    const kyc = page.getByTestId("idea-idea_client_kyc");
    const onboarding = page.getByTestId("idea-idea_client_onboarding");
    await expect(kyc).toContainText("Client KYC checks");
    await expect(kyc).toContainText("ready");
    await expect(kyc.getByTestId("stories-ready")).toHaveText("9 / 9");
    await expect(kyc.getByTestId("improvement")).toHaveText("6/7 accepted · ~275 h/month");
    await expect(kyc.getByTestId("open-questions")).toContainText("1 · waiting on sme_priya_shah");
    await expect(kyc).toContainText("100%");
    await expect(onboarding).toContainText("discovering");
    await expect(onboarding.getByTestId("stories-ready")).toHaveText("0 / 9");
    await expect(onboarding.getByTestId("open-questions")).toContainText("31");
    await expect(onboarding).toContainText("65%");
    await expect(page.getByRole("img", { name: "Flow thumbnail" })).toHaveCount(2);

    // Newest first; status filter and search narrow the list.
    await expect(page.getByRole("list", { name: "Ideas" }).getByRole("link")).toHaveCount(2);
    await page.getByLabel("Status").selectOption("ready");
    await expect(page.getByRole("list", { name: "Ideas" }).getByRole("link")).toHaveCount(1);
    await page.getByLabel("Status").selectOption("");
    await page.getByLabel("Search ideas").fill("document-led");
    await expect(page.getByTestId("idea-idea_client_onboarding")).toBeVisible();
    await expect(page.getByTestId("idea-idea_client_kyc")).toHaveCount(0);
  });

  test("AC-M12-2: the KYC Flow tab offers As-is and To-be, and Compare lists the 9 to-be tasks", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/flow");
    const views = page.getByRole("tablist", { name: "Flow view" });
    await expect(views.getByRole("tab", { name: "As-is" })).toBeVisible();
    await expect(views.getByRole("tab", { name: "To-be" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("flow-node-node_screen")).toContainText("Reviewed by Onboarding Analyst (on exceptions)");
    await views.getByRole("tab", { name: "As-is" }).click();
    await expect(page.getByTestId("flow-node-node_screen")).toContainText("~25 min per case");
    await views.getByRole("tab", { name: "Compare" }).click();
    const rows = page.getByTestId("compare-table").locator("tbody tr");
    await expect(rows).toHaveCount(9);
    await expect(rows.nth(0)).toContainText(["Request KYC documents", "Human task", "10", "Automated", "S01: automated"].join(""));
    await expect(rows.filter({ hasText: "Screen client and owners" })).toContainText("S04: automated with review");
    await expect(rows.filter({ hasText: "MLRO approval of high-risk client" })).toContainText("Unchanged");
  });

  test("clicking a step opens its story, rendered as in the stories file", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/flow");
    await page.getByTestId("flow-node-node_record_kyc").click();
    await expect(page).toHaveURL(/stories\/story_record_kyc$/);
    const story = page.getByTestId("story-markdown");
    await expect(story).toContainText("As an Onboarding Analyst, I want to write the KYC outcome to the CRM");
    await expect(story).toContainText("Change from today: Automated by suggestion S06 (today: manual, ~15 min per case).");
  });

  test("the stories table filters by priority and opens a story", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/stories");
    const rows = page.getByTestId("stories-table").locator("tbody tr");
    await expect(rows).toHaveCount(9);
    await page.getByLabel("Priority").selectOption("should");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("Chase missing documents");
    await page.getByLabel("Priority").selectOption("");
    await page.getByLabel("Has open questions").check();
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("Screen client and owners");
  });

  test("the Improvements tab lists the decided suggestions", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/improvements");
    await expect(page.getByText("6 accepted · 1 rejected")).toBeVisible();
    await expect(page.getByText("Reason: Medium-risk clients still need a person's judgement")).toBeVisible();
  });

  test("the Conversation tab shows the whole session", async ({ page }) => {
    await page.goto("/ideas/idea_client_kyc/conversation");
    await expect(page.getByRole("region", { name: "Conversation" })).toContainText("Today, what has to happen before KYC starts");
    await expect(page.getByRole("region", { name: "Conversation" })).toContainText("This conversation is complete.");
    await expect(page.getByTestId("flow-canvas")).toBeVisible();
  });

  test("New idea asks whether a process exists today and opens the conversation", async ({ page }) => {
    // The API is mocked here: a new idea's first turn needs a live LLM (cassettes only cover the samples).
    await page.route("**/api/v1/ideas", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const body = route.request().postDataJSON();
      expect(body).toMatchObject({ has_process_today: "yes", text: "Automate expense claim checks" });
      await route.fulfill({ status: 201, json: { idea_id: "idea_client_kyc", session_id: "is_client_kyc", turn: {} } });
    });
    await page.goto("/ideas/new");
    await expect(page.getByRole("button", { name: "Start the conversation" })).toBeDisabled();
    await page.getByRole("textbox", { name: "Idea" }).fill("Automate expense claim checks");
    await page.getByText("Yes", { exact: true }).click();
    await page.getByRole("button", { name: "Start the conversation" }).click();
    await expect(page).toHaveURL(/\/ideas\/idea_client_kyc\/conversation$/);
  });
});
