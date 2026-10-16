import type { Metadata } from "next";
import { ResetPassword } from "./reset-password";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Восстановление пароля — Ukladen",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function ResetPasswordPage() {
  return <ResetPassword />;
}
