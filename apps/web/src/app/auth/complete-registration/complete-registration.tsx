"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brand } from "@/shared/brand";
import "../../workspace/workspace.css";
import "../reset-password/reset-password.css";

type RegistrationState = { email: string; email_verified: boolean; password_required: boolean; complete: boolean; password_min_length: number };
const options: RequestInit = { credentials: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer" };

class RegistrationError extends Error {
  constructor(readonly status: number) { super("Registration request failed."); }
}

async function readState(): Promise<RegistrationState | null> {
  const response = await fetch("/api/v1/auth/registration", options);
  if (response.status === 401) return null;
  if (!response.ok) throw new RegistrationError(response.status);
  const data: RegistrationState = await response.json();
  if (typeof data.email !== "string" || typeof data.email_verified !== "boolean" || typeof data.password_required !== "boolean" || typeof data.complete !== "boolean" || !Number.isInteger(data.password_min_length) || data.password_min_length < 1) throw new Error("Invalid registration response.");
  return data;
}

async function write(path: string, body: Record<string, string>) {
  const csrf = await fetch("/api/v1/auth/csrf", options);
  if (!csrf.ok) throw new RegistrationError(csrf.status);
  const data: { csrf_token?: unknown } = await csrf.json();
  if (typeof data.csrf_token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(data.csrf_token)) throw new Error("Invalid CSRF response.");
  const response = await fetch(path, { ...options, method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token } });
  if (!response.ok) throw new RegistrationError(response.status);
}

function messageFor(error: unknown) {
  if (error instanceof RegistrationError) {
    if (error.status === 401) return "Сессия завершена. Войдите снова.";
    if (error.status === 400) return "Пароль не соответствует требованиям. Попробуйте более длинный пароль.";
    if (error.status === 409) return "Пароль уже задан. Обновите состояние регистрации.";
    if (error.status === 429) return "Слишком много попыток. Подождите минуту и повторите.";
    if (error.status === 403) return "Не удалось подтвердить запрос. Обновите страницу и повторите.";
  }
  return "Не удалось выполнить запрос. Проверьте соединение и попробуйте снова.";
}

function PasswordSetup({ state, onSaved }: { state: RegistrationState; onSaved: () => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const inFlight = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    if (password !== confirmation) { setMessage("Пароли не совпадают."); return; }
    inFlight.current = true;
    setBusy(true); setMessage("");
    try {
      await write("/api/v1/auth/registration/password", { password });
      setPassword(""); setConfirmation("");
      await onSaved();
    } catch (error) { setMessage(messageFor(error)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <form onSubmit={submit} aria-busy={busy}>
    <p className="auth-description">Создайте пароль Ukladen — с ним можно будет входить и без Google. Не менее {state.password_min_length} символов.</p>
    <label htmlFor="registration-password">Новый пароль Ukladen</label>
    <input id="registration-password" type="password" autoComplete="new-password" required minLength={state.password_min_length} maxLength={1024} disabled={busy} value={password} onChange={event => setPassword(event.target.value)} />
    <label htmlFor="registration-confirmation">Повторите пароль</label>
    <input id="registration-confirmation" type="password" autoComplete="new-password" required minLength={state.password_min_length} maxLength={1024} disabled={busy} value={confirmation} onChange={event => setConfirmation(event.target.value)} />
    {message && <p className="form-error" role="alert">{message}</p>}
    <button className="primary-button auth-submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить пароль"}</button>
  </form>;
}

export function CompleteRegistration() {
  const registration = useQuery({ queryKey: ["registration-status"], queryFn: readState, gcTime: 0, staleTime: 0,
    retry: false, refetchInterval: query => query.state.data && !query.state.data.complete ? 5000 : false });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const inFlight = useRef(false);
  useEffect(() => {
    if (registration.data?.complete) window.location.replace("/workspace");
  }, [registration.data?.complete]);
  useEffect(() => {
    if (!cooldown) return;
    const timer = setInterval(() => setCooldown(value => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  async function resend() {
    if (inFlight.current || cooldown) return;
    inFlight.current = true; setBusy(true); setMessage("");
    try {
      await write("/api/v1/auth/email-verification/request", {});
      setCooldown(60); setMessage("Письмо отправлено. Проверьте входящие и папку «Спам».");
    } catch (error) { setMessage(messageFor(error)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function logout() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try { await write("/api/v1/auth/logout", {}); window.location.replace("/workspace"); }
    catch (error) { setMessage(messageFor(error)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <main className="workspace-auth password-reset">
    <section className="auth-card password-reset-card" aria-labelledby="registration-title">
      <Brand /><h1 id="registration-title">Завершите регистрацию</h1>
      {registration.isPending && <p role="status">Проверяем регистрацию…</p>}
      {registration.isError && <><p className="form-error" role="alert">Не удалось проверить регистрацию.</p><button onClick={() => void registration.refetch()}>Повторить</button></>}
      {registration.data === null && <p role="status">Сессия завершена. Войдите, чтобы продолжить регистрацию.</p>}
      {registration.data && !registration.isError && <>
        <p className="auth-description">Аккаунт: {registration.data.email}</p>
        {registration.data.complete ? <p role="status">Регистрация завершена. Открываем пространство…</p>
          : registration.data.password_required ? <PasswordSetup key={registration.data.email} state={registration.data} onSaved={async () => { if (!registration.data?.email_verified) await resend(); await registration.refetch(); }} />
          : <>
            <p role="status">Подтвердите почту по ссылке из письма. До подтверждения личное пространство недоступно.</p>
            <button className="primary-button auth-submit" disabled={busy || cooldown > 0} onClick={() => void resend()}>{cooldown ? `Повторить через ${cooldown} с` : "Отправить письмо ещё раз"}</button>
            <button className="auth-recovery" disabled={busy} onClick={() => void registration.refetch()}>Я подтвердил почту — проверить</button>
          </>}
        <button className="auth-recovery" disabled={busy} onClick={() => void logout()}>Выйти</button>
      </>}
      {message && <p role="status">{message}</p>}
      <Link className="auth-recovery" href="/workspace">Вернуться ко входу</Link>
      <Link className="auth-recovery" href="/auth/reset-password">Восстановить пароль Ukladen</Link>
    </section>
  </main>;
}
