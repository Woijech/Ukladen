import { test, expect, type Page } from "@playwright/test";

const path = "/auth/reset-password";
const token = "r".repeat(43);
const csrf = "c".repeat(43);
const password = "new-private-password";

async function mockCsrf(page: Page) {
  await page.route("**/api/v1/auth/csrf", route => route.fulfill({
    headers: { "Set-Cookie": `ukladen_csrf=${csrf}; Path=/; HttpOnly; SameSite=Lax` },
    json: { csrf_token: csrf },
  }));
}

async function fillPasswords(page: Page, value = password) {
  await page.locator("form").getByLabel("Новый пароль", { exact: true }).fill(value);
  await page.getByLabel("Повторите пароль", { exact: true }).fill(value);
}

test("login links to email recovery and accepts unknown accounts without disclosure", async ({ page }) => {
  await page.route("**/api/v1/users/me", route => route.fulfill({ status: 401 }));
  await mockCsrf(page);
  const emails: string[] = [];
  await page.route("**/api/v1/auth/password-reset/request", async route => {
    const request = route.request();
    expect(request.method()).toBe("POST");
    expect(request.headers()["x-csrf-token"]).toBe(csrf);
    expect(request.headers().cookie).toContain(`ukladen_csrf=${csrf}`);
    expect(request.headers().origin).toBe("http://127.0.0.1:3001");
    expect(request.headers().referer).toBeUndefined();
    emails.push(request.postDataJSON().email);
    await route.fulfill({ status: 202, json: { detail: "Password reset request accepted." } });
  });
  await page.goto("/workspace");
  await page.getByRole("link", { name: "Забыли пароль?" }).click();
  await expect(page).toHaveURL(path);
  for (const email of ["member@example.com", "unknown@example.com"]) {
    await page.getByLabel("Электронная почта", { exact: true }).fill(email);
    await page.getByRole("button", { name: "Отправить ссылку" }).click();
    await expect(page.getByRole("status")).toContainText("Если для этой почты есть подходящий аккаунт");
    await page.getByRole("button", { name: "Запросить ещё раз" }).click();
  }
  expect(emails).toEqual(["member@example.com", "unknown@example.com"]);
});

test("confirmation requires a matching password and one explicit CSRF-protected submission", async ({ page }) => {
  await mockCsrf(page);
  let confirmations = 0;
  await page.route("**/api/v1/auth/password-reset/confirm", async route => {
    confirmations++;
    const request = route.request();
    expect(request.method()).toBe("POST");
    expect(request.postDataJSON()).toEqual({ token, new_password: password });
    expect(request.headers()["x-csrf-token"]).toBe(csrf);
    expect(request.headers().cookie).toContain(`ukladen_csrf=${csrf}`);
    expect(request.headers().origin).toBe("http://127.0.0.1:3001");
    expect(request.headers().referer).toBeUndefined();
    expect(request.url()).not.toContain(token);
    await route.fulfill({ status: 204 });
  });
  await page.goto(`${path}#token=${token}`);
  await expect(page.getByRole("heading", { name: "Новый пароль" })).toBeVisible();
  await expect(page).toHaveURL(path);
  expect(confirmations).toBe(0);
  expect(await page.content()).not.toContain(token);
  await fillPasswords(page);
  await page.getByLabel("Повторите пароль").fill("different-password");
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("Пароли не совпадают.");
  expect(confirmations).toBe(0);
  await fillPasswords(page);
  await page.locator("form").evaluate((form: HTMLFormElement) => { form.requestSubmit(); form.requestSubmit(); });
  await expect(page.getByRole("status")).toContainText("Предыдущие сессии аккаунта завершены");
  expect(confirmations).toBe(1);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  await page.reload();
  await expect(page.getByLabel("Электронная почта")).toBeVisible();
});

test("expired or used tokens offer a new email and never resubmit the secret", async ({ page }) => {
  await mockCsrf(page);
  await page.route("**/api/v1/auth/password-reset/confirm", route => route.fulfill({
    status: 400, json: { detail: "Invalid or expired token." },
  }));
  await page.goto(`${path}#token=${token}`);
  await fillPasswords(page);
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Ссылка недействительна");
  await page.getByRole("button", { name: "Запросить новую ссылку" }).click();
  await expect(page.getByLabel("Электронная почта")).toHaveValue("");
  await expect(page.locator("form").getByLabel("Новый пароль", { exact: true })).toHaveCount(0);
});

test("a stricter server password policy allows correction with the same token", async ({ page }) => {
  await mockCsrf(page);
  let confirmations = 0;
  await page.route("**/api/v1/auth/password-reset/confirm", async route => {
    expect(route.request().postDataJSON().token).toBe(token);
    confirmations++;
    await route.fulfill(confirmations === 1
      ? { status: 400, json: { detail: "New password does not meet the password policy." } }
      : { status: 204 });
  });
  await page.goto(`${path}#token=${token}`);
  await fillPasswords(page);
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("не соответствует требованиям");
  await fillPasswords(page, password.repeat(2));
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByRole("heading", { name: "Пароль изменён" })).toBeVisible();
  expect(confirmations).toBe(2);
});

for (const action of ["request", "confirm"] as const) {
  for (const status of [403, 429, 503]) {
    test(`${action} handles ${status}, logs no credentials and allows retry`, async ({ page }) => {
      await mockCsrf(page);
      const diagnostics: string[] = [];
      page.on("console", message => {
        if (message.text().startsWith('{"event":"web.')) diagnostics.push(message.text());
      });
      let attempts = 0;
      await page.route(`**/api/v1/auth/password-reset/${action}`, async route => {
        attempts++;
        await route.fulfill({ status: attempts === 1 ? status : action === "request" ? 202 : 204,
          headers: { "X-Request-ID": "a".repeat(32) } });
      });
      await page.goto(path + (action === "confirm" ? `#token=${token}` : ""));
      if (action === "confirm") await fillPasswords(page);
      else await page.getByLabel("Электронная почта").fill("private@example.com");
      const submit = page.getByRole("button", { name: action === "request" ? "Отправить ссылку" : "Сохранить пароль" });
      await submit.click();
      await expect(page.getByRole("main").getByRole("alert")).toContainText(status === 429 ? "Слишком много попыток" : status === 403 ? "Не удалось подтвердить запрос" : "временно недоступен");
      expect(diagnostics.map(entry => JSON.parse(entry))).toContainEqual({
        event: "web.password_reset_failed", stage: action === "confirm" ? "confirmation" : "request",
        status_code: status, request_id: "a".repeat(32),
      });
      for (const secret of [token, csrf, password, "private@example.com"]) expect(diagnostics.join("\n")).not.toContain(secret);
      await submit.click();
      await expect(page.getByRole("status")).toContainText(action === "request" ? "Если для этой почты" : "Пароль сохранён");
      expect(attempts).toBe(2);
    });
  }
}

for (const failure of ["invalid", "network", "unavailable"]) {
  test(`CSRF ${failure} never submits a reset and permits a fresh retry`, async ({ page }) => {
    let confirmations = 0;
    await page.route("**/api/v1/auth/csrf", route => failure === "network" ? route.abort()
      : route.fulfill(failure === "invalid" ? { json: { csrf_token: "invalid" } } : { status: 503 }));
    await page.route("**/api/v1/auth/password-reset/confirm", async route => {
      confirmations++;
      await route.fulfill({ status: 204 });
    });
    await page.goto(`${path}#token=${token}`);
    await fillPasswords(page);
    await page.getByRole("button", { name: "Сохранить пароль" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    expect(confirmations).toBe(0);
    await mockCsrf(page);
    await page.getByRole("button", { name: "Сохранить пароль" }).click();
    await expect(page.getByRole("heading", { name: "Пароль изменён" })).toBeVisible();
    expect(confirmations).toBe(1);
  });
}

for (const suffix of ["#token=invalid", `#token=${token}&token=${token}`, `?token=${token}`, `?preview=1#token=${token}`]) {
  test(`invalid link ${suffix} cannot call the API`, async ({ page }) => {
    const requests: string[] = [];
    await page.route("**/api/v1/auth/**", async route => {
      requests.push(route.request().url());
      await route.fulfill({ status: 500 });
    });
    await page.goto(path + suffix);
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Ссылка недействительна");
    await expect(page).toHaveURL(path);
    expect(requests).toEqual([]);
  });
}

test("opening another email link replaces the token used by the form", async ({ page }) => {
  await mockCsrf(page);
  const nextToken = "n".repeat(43);
  await page.route("**/api/v1/auth/password-reset/confirm", async route => {
    expect(route.request().postDataJSON().token).toBe(nextToken);
    await route.fulfill({ status: 204 });
  });
  await page.goto(`${path}#token=${token}`);
  await fillPasswords(page);
  await page.evaluate(value => { location.hash = `token=${value}`; }, nextToken);
  await expect(page.locator("form").getByLabel("Новый пароль", { exact: true })).toHaveValue("");
  await expect(page).toHaveURL(path);
  await fillPasswords(page);
  await page.getByRole("button", { name: "Сохранить пароль" }).click();
  await expect(page.getByRole("heading", { name: "Пароль изменён" })).toBeVisible();
});

test("email previews cannot reset a password and receive privacy headers", async ({ request }) => {
  const response = await request.get(`${path}#token=${token}`);
  expect(response.status()).toBe(200);
  expect(response.headers()["referrer-policy"]).toBe("no-referrer");
  expect(response.headers()["cache-control"]).toContain("no-store");
  expect(response.headers()["x-robots-tag"]).toContain("noindex");
  expect(await response.text()).not.toContain(token);
});
