import type { Metadata } from "next";
import Link from "next/link";
import { Brand } from "@/shared/brand";
import { GoogleAuth } from "@/shared/google-auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Не удалось войти через Google — Ukladen",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function AuthErrorPage() {
  return <main>
    <header><Brand /></header>
    <section aria-labelledby="google-error-title">
      <h1 id="google-error-title">Не удалось войти через Google</h1>
      <p>Вход отменён, ссылка устарела или сервис временно недоступен. Попробуйте ещё раз.</p>
      <p>Если вы уже регистрировались с этой почтой, войдите по паролю и выберите «Связать с Google» в меню профиля.</p>
      <GoogleAuth />
      <p><Link href="/workspace">Вернуться ко входу по почте</Link></p>
    </section>
  </main>;
}
