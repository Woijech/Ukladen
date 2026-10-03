import type { Metadata } from "next";
import { VerifyEmail } from "./verify-email";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Подтверждение почты — Ukladen",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function VerifyEmailPage() {
  return <VerifyEmail />;
}
