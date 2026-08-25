import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { ToastProvider } from "@/components/toast";
import { LanguageProvider } from "@/lib/i18n";

// Two families, as the stylesheet has always asked for: Inter carries the
// interface text, where it stays legible down to the smallest label, and Manrope
// carries headings and the wordmark. Both are loaded as variable fonts so the
// weight range costs a single file each.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });

export const metadata: Metadata = {
  title: "OpenLivery — AI agents for your agency",
  description: "Open source platform to build and manage AI agents.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${manrope.variable}`}>
        <LanguageProvider>
          <ToastProvider>
            <AppShell>{children}</AppShell>
          </ToastProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
