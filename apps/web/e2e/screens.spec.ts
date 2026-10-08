import { test } from "@playwright/test";
import { seed, signIn } from "./helpers";

// Not an assertion suite: captures the main screens for design review. Run with SCREENSHOTS=1.
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to capture screens");

test("capture screens", async ({ page, request }) => {
  const out = process.env.SCREENSHOTS!;
  await seed(request, "samples");
  await signIn(page, request);
  for (const [name, path] of [["ideas", "/"], ["overview", "/ideas/idea_client_kyc"],
    ["flow", "/ideas/idea_client_kyc/flow"], ["stories", "/ideas/idea_client_kyc/stories"],
    ["story", "/ideas/idea_client_kyc/stories/story_screen"], ["conversation", "/ideas/idea_client_kyc/conversation"],
    ["improvements", "/ideas/idea_client_kyc/improvements"], ["new", "/ideas/new"]]) {
    await page.goto(path);
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: false });
  }
  await page.goto("/ideas/idea_client_kyc/flow");
  await page.getByRole("tab", { name: "Compare" }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/compare.png` });
});
