import type { Metadata } from "next";
import { Providers } from "@/shared/providers";
import symbol from "@/shared/assets/ukladen-avatar.png";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ukladen",
  description: "Ukladen — a personal student workspace for BSUIR students.",
  icons: { icon: { url: symbol.src, type: "image/png" }, apple: symbol.src },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
