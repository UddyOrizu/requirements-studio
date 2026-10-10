import { expect, test } from "@playwright/test";
import { lastEmail, seed, switchUser } from "./helpers";

test.describe("Approvals", () => {
  test.beforeEach(async ({ request }) => { await seed(request, "samples"); });

  // "Ask someone" on a story emails a colleague, who answers from their inbox; the requester sees the answer.
  test("A question asked on a story is emailed, answered from the inbox, and shown in the conversation", async ({ page, request }) => {
    await switchUser(page, request, "user_sarah_lin");
    await page.goto("/ideas/idea_client_kyc/stories/story_record_kyc");
    await page.getByLabel("Question").fill("Who approves a high-risk client?");
    await page.getByLabel("Who").selectOption({ label: "Priya Shah · priya.shah@example.com" });
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Asked Priya Shah (MLRO): Who approves a high-risk client?")).toBeVisible();
    expect((await lastEmail(request, "priya.shah@example.com")).subject)
      .toBe("Sarah Lin asks you to answer a question: Who approves a high-risk client?");

    await switchUser(page, request, "user_priya_shah");
    await page.goto("/approvals");
    await expect(page.getByLabel("1 waiting")).toBeVisible();
    await page.getByTestId("approvals-list").getByText("Who approves a high-risk client?").click();
    await page.getByLabel("Your answer").fill("The MLRO, with the engagement partner informed.");
    await page.getByRole("button", { name: "Send answer" }).click();
    await expect(page.getByTestId("approval-status")).toHaveText("answered");
    await expect(page.getByLabel("1 waiting")).toHaveCount(0);

    await switchUser(page, request, "user_sarah_lin");
    await page.goto("/ideas/idea_client_kyc/conversation");
    await expect(page.getByText("Priya Shah answered: The MLRO, with the engagement partner informed.")).toBeVisible();
    expect((await lastEmail(request, "sarah.lin@example.com")).subject)
      .toBe("Priya Shah answered: Who approves a high-risk client?");
  });

  // A proposed change goes to the process owner, who approves it from the email link.
  test("A proposed change is approved by the process owner", async ({ page, request }) => {
    const admin = (await (await request.post("http://localhost:8799/dev/token", { form: { username: "user_admin" } })).json()).access_token;
    const res = await request.post("http://localhost:8799/api/v1/processes/proc_client_onboarding/patches", {
      headers: { Authorization: `Bearer ${admin}` },
      data: { patch_id: "p_e2e_review", process_id: "proc_client_onboarding", base_version: 3, auto_apply: false,
              status: "proposed", author: { kind: "user", id: "user_admin" }, reason: "Name the screening step after what it does",
              ops: [{ op: "replace", path: "/nodes/node_screening/name", value: "Screen the client" }] },
    });
    expect(res.status()).toBe(202);
    const mail = await lastEmail(request, "daniel.okafor@example.com");
    const link = mail.text.match(/\/approvals\/apr_\w+/)![0];

    await switchUser(page, request, "user_daniel_okafor");
    await page.goto(link);
    await expect(page.getByRole("heading", { name: "Name the screening step after what it does" })).toBeVisible();
    await expect(page.getByTestId("patch-ops")).toContainText("replace /nodes/node_screening/name");
    await page.getByLabel("Note").fill("Clearer, thanks");
    await page.getByRole("button", { name: "Approve change" }).click();
    await expect(page.getByTestId("approval-status")).toHaveText("approved");
    await expect(page.getByText("Proposed change · applied")).toBeVisible();
  });
});
