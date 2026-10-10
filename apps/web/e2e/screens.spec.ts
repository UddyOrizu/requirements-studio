import { test } from "@playwright/test";
import { API, seed, signIn, switchUser, token } from "./helpers";

// Not an assertion suite: captures the main screens for design review. Run with SCREENSHOTS=<dir>.
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=<dir> to capture screens");

test("capture screens", async ({ page, request }) => {
  const out = process.env.SCREENSHOTS!;
  await seed(request, "samples");
  await page.goto("/signin");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/signin.png` });
  await signIn(page, request);
  for (const [name, path] of [["ideas", "/"], ["overview", "/ideas/idea_client_kyc"],
    ["flow", "/ideas/idea_client_kyc/flow"], ["stories", "/ideas/idea_client_kyc/stories"],
    ["story", "/ideas/idea_client_kyc/stories/story_screen"], ["conversation", "/ideas/idea_client_kyc/conversation"],
    ["improvements", "/ideas/idea_client_kyc/improvements"], ["new", "/ideas/new"],
    ["export", "/ideas/idea_client_kyc/export"], ["export-draft", "/ideas/idea_client_onboarding/export"]]) {
    await page.goto(path);
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: false });
  }
  await page.goto("/ideas/idea_client_kyc/flow");
  await page.getByRole("tab", { name: "Compare" }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/compare.png` });
});

test("capture user and approval screens", async ({ page, request }) => {
  const out = process.env.SCREENSHOTS!;
  await seed(request, "samples");
  const admin = await token(request, "user_admin");
  await request.post(`${API}/api/v1/admin/users`, { headers: { Authorization: `Bearer ${admin}` },
    data: { name: "Morgan Ellis", email: "morgan.ellis@example.com" } });
  await request.post(`${API}/api/v1/processes/proc_client_onboarding/patches`, {
    headers: { Authorization: `Bearer ${admin}` },
    data: { patch_id: "p_screens", process_id: "proc_client_onboarding", base_version: 3, auto_apply: false,
            status: "proposed", author: { kind: "user", id: "user_admin" }, reason: "Name the screening step after what it does",
            ops: [{ op: "replace", path: "/nodes/node_screening/name", value: "Screen the client" }] } });
  await switchUser(page, request, "user_admin");
  await page.goto("/admin/users");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/users.png` });
  await switchUser(page, request, "user_daniel_okafor");
  await page.goto("/approvals");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/approvals.png` });
  await page.getByTestId("approvals-list").locator("a").first().click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/approval.png` });
  await page.goto("/ideas/idea_client_kyc/stories/story_screen");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/story-ask.png`, fullPage: true });
});
