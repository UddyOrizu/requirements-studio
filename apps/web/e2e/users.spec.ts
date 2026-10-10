import { expect, test } from "@playwright/test";
import { DEV_PASSWORD, lastEmail, seed } from "./helpers";

// Internal accounts: password sign-in, and an admin inviting someone who sets a password from the email link.
test.describe("Users", () => {
  test.beforeEach(async ({ request }) => { await seed(request, "samples"); });

  test("Password sign-in, a wrong password is refused, and users do not see user management", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/signin$/);
    await page.getByLabel("Email").fill("sarah.lin@example.com");
    await page.getByLabel("Password").fill("not the password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Email or password is incorrect");

    await page.getByLabel("Password").fill(DEV_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Ideas" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Sarah Lin" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Users" })).toHaveCount(0);
    await page.goto("/admin/users");
    await expect(page.getByText("Only administrators can manage users.")).toBeVisible();
  });

  test("An admin invites a colleague, who sets a password from the email and signs in", async ({ page, request }) => {
    await page.goto("/signin");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill(DEV_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByRole("link", { name: "Users" }).click();
    await expect(page.getByTestId("user-user_sarah_lin")).toContainText("active");

    await page.getByRole("button", { name: "Add user" }).click();
    await page.getByLabel("Full name").fill("Morgan Ellis");
    await page.getByLabel("Email").fill("morgan.ellis@example.com");
    await page.getByRole("button", { name: "Add and invite" }).click();
    await expect(page.getByRole("status")).toHaveText("Invitation sent to morgan.ellis@example.com.");
    await expect(page.getByTestId("user-user_morgan_ellis")).toContainText("invited");

    const invite = await lastEmail(request, "morgan.ellis@example.com");
    expect(invite.subject).toBe("You have been invited to Requirements Studio");
    const link = invite.text.match(/https?:\/\/\S+\/set-password\?token=[\w-]+/)![0];
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.goto(link.replace(/^https?:\/\/[^/]+/, ""));
    await expect(page.getByRole("heading", { name: "Welcome, Morgan Ellis" })).toBeVisible();
    await page.getByLabel("New password").fill("a long enough phrase");
    await page.getByLabel("Confirm password").fill("a long enough phrase");
    await page.getByRole("button", { name: "Set password and sign in" }).click();
    await expect(page.getByRole("link", { name: "Morgan Ellis" })).toBeVisible();
  });
});
