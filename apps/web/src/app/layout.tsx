import type { Metadata } from "next";
import { Providers } from "@/shared/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ukladen",
  description: "Ukladen — a personal student workspace for BSUIR students.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
