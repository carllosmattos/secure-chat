import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Secure Chat",
  description: "Chat corporativo com detecção de PII e segredos",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
