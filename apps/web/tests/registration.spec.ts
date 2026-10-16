import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace } from "./workspace-fixtures";

const csrf = "c".repeat(43);
const password = "private-new-password-123";
const token = "t".repeat(43);

async function pendingRegistration(page: Page, passwordRequired = false, verified = false) {
  const workspace = await mockWorkspace(page);
  const state = { email: "student@example.com", passwordRequired, verified, status: 200, passwordStatus: 204, resendStatus: 202, passwordWrites: 0, resendWrites: 0 };
  await page.route("**/api/v1/auth/registration", route => route.fulfill({ status: state.status,
    json: { email: state.email, email_verified: state.verified, password_required: state.passwordRequired,
      complete: state.verified && !state.passwordRequired, password_min_length: 12 } }));
  await page.route("**/api/v1/auth/registration/password", async route => {
    state.passwordWrites++;
    const request = route.request();
    expect(request.method()).toBe("POST");
    expect(request.postDataJSON()).toEqual({ password });
    expect(request.headers()["x-csrf-token"]).toBe(csrf);
    expect(request.headers().cookie).toContain(`ukladen_csrf=${csrf}`);
    expect(request.headers().origin).toBe("http://127.0.0.1:3001");
    expect(request.headers().referer).toBeUndefined();
    if (state.passwordStatus === 204) state.passwordRequired = false;
    await route.fulfill({ status: state.passwordStatus });
  });
  await page.route("**/api/v1/auth/email-verification/request", async route => {
    state.resendWrites++;
    expect(route.request().postDataJSON()).toEqual({});
    expect(route.request().headers()["x-csrf-token"]).toBe(csrf);
    await route.fulfill({ status: state.resendStatus, json: {} });
  });
  return { state, workspace };
}

test("an unverified existing session is redirected before private calendar reads", async ({ page }) => {
  const { workspace } = await pendingRegistration(page);
  workspace.registrationComplete = false;
  let calendarReads = 0;
  await page.route("**/api/v1/calendar/**", route => { calendarReads++; return route.fulfill({ status: 500 }); });
  await page.goto("/workspace");
  await expect(page).toHaveURL("/auth/complete-registration");
  await expect(page.getByRole("status")).toContainText("Подтвердите почту");
  expect(calendarReads).toBe(0);
  await expect(page.locator(".workspace-shell")).toHaveCount(0);
});

test("verification can be resent once, respects cooldown and detects completion", async ({ page }) => {
  const { state } = await pendingRegistration(page);
  const response = await page.goto("/auth/complete-registration");
  expect(response?.headers()["cache-control"]).toContain("no-store");
  expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
  const resend = page.getByRole("button", { name: "Отправить письмо ещё раз" });
  await resend.evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole("button", { name: /Повторить через/ })).toBeDisabled();
  expect(state.resendWrites).toBe(1);
  state.verified = true;
  await page.getByRole("button", { name: "Я подтвердил почту — проверить" }).click();
  await expect(page).toHaveURL("/workspace");
  await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
});

for (const mobile of [false, true]) {
  test(`Google signup requires a new Ukladen password on ${mobile ? "mobile" : "desktop"}`, async ({ page }) => {
    const { state } = await pendingRegistration(page, true, true);
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/auth/complete-registration");
    await page.getByLabel("Новый пароль Ukladen").fill(password);
    await page.getByLabel("Повторите пароль").fill("different-password-123");
    await page.getByRole("button", { name: "Сохранить пароль" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Пароли не совпадают");
    expect(state.passwordWrites).toBe(0);
    await page.getByLabel("Повторите пароль").fill(password);
    await page.getByRole("button", { name: "Сохранить пароль" }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
    await expect(page).toHaveURL("/workspace");
    expect(state.passwordWrites).toBe(1);
    expect(state.resendWrites).toBe(0);
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  });
}

test("third-party Google signup requests our email proof after setting a password", async ({ page }) => {
  const { state } = await pendingRegistration(page, true, false);
  await page.goto("/auth/complete-registration");
  await page.getByLabel("Новый пароль Ukladen").fill(password);
  await page.getByLabel("Повторите пароль").fill(password);
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Подтвердите почту" })).toBeVisible();
  expect(state.passwordWrites).toBe(1);
  expect(state.resendWrites).toBe(1);
  await expect(page.getByLabel("Новый пароль Ukladen")).toHaveCount(0);
});

for (const status of [400, 403, 409, 429, 503]) {
  test(`password setup ${status} cannot finish signup and can recover`, async ({ page }) => {
    const { state } = await pendingRegistration(page, true, true);
    state.passwordStatus = status;
    await page.goto("/auth/complete-registration");
    await page.getByLabel("Новый пароль Ukladen").fill(password);
    await page.getByLabel("Повторите пароль").fill(password);
    await page.getByRole("button", { name: "Сохранить пароль" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL("/auth/complete-registration");
    expect(state.passwordRequired).toBe(true);
    state.passwordStatus = 204;
    await page.getByRole("button", { name: "Сохранить пароль" }).click();
    await expect(page).toHaveURL("/workspace");
  });
}

test("expiry and account changes discard the pending password form", async ({ page }) => {
  const { state } = await pendingRegistration(page, true, true);
  await page.goto("/auth/complete-registration");
  await page.getByLabel("Новый пароль Ukladen").fill(password);
  state.email = "another@example.com";
  await page.clock.fastForward(5000);
  await expect(page.getByText("Аккаунт: another@example.com")).toBeVisible();
  await expect(page.getByLabel("Новый пароль Ukladen")).toHaveValue("");
  state.status = 401;
  await page.clock.fastForward(5000);
  await expect(page.getByRole("status")).toContainText("Сессия завершена");
  await expect(page.getByLabel("Новый пароль Ukladen")).toHaveCount(0);
  expect(state.passwordWrites).toBe(0);
});

for (const status of [204, 400, 503]) {
  test(`Google email link is private, requires explicit confirmation and handles ${status}`, async ({ page }) => {
    await mockWorkspace(page);
    let confirmations = 0;
    await page.route("**/api/v1/auth/google/email/confirm", async route => {
      confirmations++;
      expect(route.request().postDataJSON()).toEqual({ token });
      expect(route.request().headers()["x-csrf-token"]).toBe(csrf);
      expect(route.request().headers().referer).toBeUndefined();
      await route.fulfill({ status });
    });
    const response = await page.goto(`/auth/confirm-google-link#token=${token}`);
    expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
    await expect(page).toHaveURL("/auth/confirm-google-link");
    const button = page.getByRole("button", { name: "Подтвердить вход через Google", exact: true });
    await expect(button).toBeVisible();
    expect(confirmations).toBe(0);
    expect(await page.locator("body").innerText()).not.toContain(token);
    await button.evaluate((element: HTMLButtonElement) => { element.click(); element.click(); });
    if (status === 204) await expect(page).toHaveURL("/workspace");
    else await expect(page.getByRole("status")).toContainText(status === 400 ? "Ссылка недействительна" : "Не удалось подтвердить");
    expect(confirmations).toBe(1);
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  });
}

test("Google email confirmation previews and malformed links never submit a proof", async ({ page, request }) => {
  let writes = 0;
  await page.route("**/api/v1/**", route => { writes++; return route.fulfill({ status: 500 }); });
  const response = await request.get("/auth/confirm-google-link");
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toContain("no-store");
  await page.goto("/auth/confirm-google-link#token=invalid");
  await expect(page.getByRole("status")).toContainText("Ссылка недействительна");
  expect(writes).toBe(0);
});
