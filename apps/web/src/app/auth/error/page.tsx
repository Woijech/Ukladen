import type { Metadata } from "next";
import Link from "next/link";
import { Brand } from "@/shared/brand";
import { GoogleAuth } from "@/shared/google-auth";
import styles from "@/shared/google-auth.module.css";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Не удалось войти через Google — Ukladen",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function AuthErrorPage({ searchParams }: { searchParams: Promise<{ reason?: string | string[] }> }) {
  const reason = (await searchParams).reason;
  const linking = reason === "account_linking_required";
  const emailConfirmation = reason === "google_email_confirmation_required";
  return <main className={styles.recovery}>
    <header><Brand /></header>
    <section aria-labelledby="google-error-title">
      {emailConfirmation ? <>
        <h1 id="google-error-title">Подтвердите вход по письму</h1>
        <p>Мы отправили ссылку на почту Google-аккаунта. Откройте её в этом же браузере и подтвердите вход, чтобы связать аккаунты. Ссылка действует 10 минут.</p>
        <p>Проверьте входящие и папку «Спам». Если письмо не пришло или ссылка устарела, начните вход через Google заново.</p>
        <GoogleAuth />
      </> : linking ? <>
        <h1 id="google-error-title">Свяжем Google с вашим аккаунтом</h1>
        <p>С этой почтой уже есть аккаунт Ukladen. Подтвердите его почту и пароль один раз, затем выберите аккаунт Google для привязки. Ваши данные сохранятся.</p>
        <GoogleAuth link signIn />
        <p><Link href="/auth/reset-password">Забыли пароль Ukladen?</Link></p>
      </> : <>
        <h1 id="google-error-title">Не удалось войти через Google</h1>
        <p>Вход отменён, ссылка устарела или сервис временно недоступен. Попробуйте ещё раз.</p>
        <p>Если вы уже регистрировались с этой почтой, <Link href="/auth/error?reason=account_linking_required">войдите и свяжите аккаунт с Google</Link>.</p>
        <GoogleAuth />
      </>}
      <p><Link href="/workspace">Вернуться ко входу по почте</Link></p>
    </section>
  </main>;
}
