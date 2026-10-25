import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("original public content, immutable assets, appearance and same-domain sign in", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Intelligence behind every trade." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Approach", exact: true })).toHaveAttribute("href", "#approach");
  await expect(page.getByRole("link", { name: "Platform", exact: true })).toHaveAttribute("href", "#platform");
  const assets = JSON.parse(readFileSync(resolve("../docs/merger/protected-assets.json"), "utf8"));
  for (const [file, expected] of Object.entries(assets)) {
    const url = file.replace("frontend/public", "").replace("frontend/src/app/favicon.ico", "/favicon.ico");
    const response = await page.request.get(url);
    expect(response.ok(), url).toBeTruthy();
    expect(createHash("sha256").update(await response.body()).digest("hex")).toBe(expected);
  }
  await page.getByLabel("Theme", { exact: true }).selectOption("classic-light");
  await page.getByLabel("Accent color").selectOption("purple");
  await page.reload();
  await expect(page.getByLabel("Theme", { exact: true })).toHaveValue("classic-light");
  await expect(page.getByLabel("Accent color")).toHaveValue("purple");
  expect(await page.evaluate(() => document.documentElement.hasAttribute("data-theme"))).toBe(false);
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  expect(await page.locator(".auth-panel").evaluate(element => getComputedStyle(element).getPropertyValue("--accent"))).toBe("");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile public navigation and protected compatibility routes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/workspace");
  await expect(page.getByRole("heading", { name: "Your edge starts here." })).toBeVisible();
  await page.goto("/admin/login");
  await expect(page.getByRole("heading", { name: "Administrator sign in" })).toBeVisible();
});

test("integrated registration, dashboard, manual paper fill and admin rejection", async ({ page }) => {
  const email = `browser-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Browser Trader");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.locator('input[name="password"]').fill("Browser-test-password-123!");
  await page.getByLabel("Confirm password", { exact: true }).fill("Browser-test-password-123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Your account is ready");
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Your edge starts here, Browser." })).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
  const rejected = await page.request.get("/api/v1/admin/users");
  expect(rejected.status()).toBe(403);
  const health = await (await page.request.get("/api/health")).json();
  expect(health).toMatchObject({ mode: "paper", live_trading: false });
  await page.getByRole("button", { name: "New paper order", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("spinbutton").fill("2");
  await dialog.getByRole("button", { name: "Submit paper buy" }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Orders", exact: true }).click();
  await page.getByRole("button", { name: "Simulate fill", exact: true }).click();
  await expect(page.getByRole("cell", { name: "filled", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your edge starts here, Browser." })).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});


test("fragment recovery tokens and older verification links remain compatible", async ({ page }) => {
  const email = `recovery-${Date.now()}@example.com`;
  const headers = { Origin: "http://127.0.0.1:13000" };
  const registered = await page.request.post("/api/v1/auth/register", {
    headers, data: { name: "Recovery Trader", email, password: "Original-browser-password-123!" },
  });
  expect(registered.status()).toBe(201);
  const verificationUrl = (await registered.json()).development_verification_url as string;
  expect(verificationUrl).toContain("#token=");
  await page.request.post("/api/v1/auth/logout", { headers });
  const recovery = await page.request.post("/api/v1/auth/forgot-password", { headers, data: { email } });
  const resetUrl = (await recovery.json()).development_url as string;
  expect(resetUrl).toContain("#token=");
  await page.goto(resetUrl);
  await page.locator('input[name="password"]').fill("Replacement-browser-password-456!");
  await page.locator('input[name="confirm_password"]').fill("Replacement-browser-password-456!");
  await page.getByRole("button", { name: "Save new password", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Password updated");
  const login = await page.request.post("/api/v1/auth/login", {
    headers, data: { email, password: "Replacement-browser-password-456!" },
  });
  expect(login.status()).toBe(200);
  // Pre-merger email links with query tokens continue to work during cutover.
  await page.goto(verificationUrl.replace("#token=", "?token="));
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Email verified");
  const profile = await page.request.get("/api/v1/profile");
  expect((await profile.json()).email_verified).toBe(true);
});

test("mock broker connection, health, sync and disconnect stay server-side", async ({ page }) => {
  const email = `mock-broker-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Mock Broker Trader");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.locator('input[name="password"]').fill("Mock-broker-browser-password-123!");
  await page.getByLabel("Confirm password", { exact: true }).fill("Mock-broker-browser-password-123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Your account is ready");

  await page.goto("/settings/brokers");
  await expect(page.getByRole("heading", { name: "Broker connections" }).first()).toBeVisible();
  await expect(page.getByText("Zerodha", { exact: true })).toBeVisible();
  await expect(page.getByText("Not implemented · No credentials collected").first()).toBeVisible();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByText("Mock broker disconnected.")).toBeVisible();
  await page.getByRole("button", { name: "Connect mock broker", exact: true }).click();
  await expect(page.getByText("Mock paper broker connected.")).toBeVisible();
  await expect(page.getByText("Status: connected")).toBeVisible();

  await page.getByRole("button", { name: "Check health", exact: true }).click();
  await expect(page.getByText("Mock broker health: connected.")).toBeVisible();
  await page.getByRole("button", { name: "Sync paper data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Last mock synchronization" })).toBeVisible();
  await expect(page.getByText("INR 1000000").first()).toBeVisible();

  const exposedSecrets = await page.evaluate(() => {
    const values = [...Object.values(localStorage), ...Object.values(sessionStorage)].join(" ");
    return /access[_-]?token|secret|mock-broker-token/i.test(values);
  });
  expect(exposedSecrets).toBe(false);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByText("Mock broker disconnected.")).toBeVisible();
  const status = await page.request.get("/api/v1/settings/brokers");
  expect((await status.json()).connections[0].status).toBe("disconnected");
});
