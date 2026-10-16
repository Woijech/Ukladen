import type { Metadata } from "next";
import { CompleteRegistration } from "./complete-registration";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Завершение регистрации — Ukladen",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function CompleteRegistrationPage() {
  return <CompleteRegistration />;
}
