import type { Metadata } from "next";
import { VerifyEmail } from "../verify-email/verify-email";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Подтверждение Google-входа — Ukladen",
  robots: { index: false, follow: false }, referrer: "no-referrer",
};

export default function ConfirmGoogleLinkPage() { return <VerifyEmail googleLink />; }
