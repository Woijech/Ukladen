"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type VerificationStatus = "pending" | "success" | "invalid" | "limited" | "error";

const messages: Record<VerificationStatus, string> = {
  pending: "Подтверждаем вашу почту…",
  success: "Почта подтверждена. Теперь можно вернуться в Ukladen.",
  invalid: "Ссылка недействительна, уже использована или срок её действия истёк. Запросите новое письмо.",
  limited: "Слишком много попыток. Откройте ссылку из письма позже.",
  error: "Не удалось подтвердить почту. Попробуйте снова открыть ссылку из письма позже.",
};

async function confirmEmail(token: string | null): Promise<VerificationStatus> {
  if (!token || !/^[A-Za-z0-9_-]{43}$/.test(token)) return "invalid";
  try {
    const csrf = await fetch("/api/v1/auth/csrf", {
      credentials: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer",
    });
    if (!csrf.ok) return csrf.status === 429 ? "limited" : "error";
    const data: { csrf_token?: unknown } = await csrf.json();
    if (typeof data.csrf_token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(data.csrf_token)) {
      return "error";
    }
    const response = await fetch("/api/v1/auth/email-verification/confirm", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token },
      body: JSON.stringify({ token }),
    });
    if (response.status === 204) return "success";
    if (response.status === 400) return "invalid";
    return response.status === 429 ? "limited" : "error";
  } catch {
    return "error";
  }
}

export function VerifyEmail() {
  const [status, setStatus] = useState<VerificationStatus>("pending");
  const confirmation = useRef<Promise<VerificationStatus> | null>(null);

  useEffect(() => {
    if (!confirmation.current) {
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      const tokens = fragment.getAll("token");
      const token = tokens.length === 1 ? tokens[0] : null;
      window.history.replaceState(window.history.state, "", window.location.pathname);
      // Reuse the promise when React repeats effects; one-time tokens must be submitted once.
      confirmation.current = confirmEmail(token);
    }
    let mounted = true;
    void confirmation.current.then(result => { if (mounted) setStatus(result); });
    // Opening another email link on this page starts a fresh confirmation.
    const openAnotherLink = () => window.location.reload();
    window.addEventListener("hashchange", openAnotherLink);
    return () => {
      mounted = false;
      window.removeEventListener("hashchange", openAnotherLink);
    };
  }, []);

  return (
    <main>
      <header><span className="brand">Ukladen</span></header>
      <section aria-labelledby="verification-title">
        <h1 id="verification-title">Подтверждение почты</h1>
        <p role="status" aria-live="polite">{messages[status]}</p>
        <Link href="/">Вернуться на главную</Link>
      </section>
    </main>
  );
}
