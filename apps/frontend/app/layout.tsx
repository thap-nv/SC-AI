import "./globals.css";
import type { Metadata } from "next";
import { Be_Vietnam_Pro, JetBrains_Mono, Sarabun } from "next/font/google";
import Providers from "@/components/providers";

// Sarabun is the UI face of viettelidc.com.vn and carries every user-entered name (full Vietnamese subset).
// Be Vietnam Pro stands in for the brand's FS PF BeauSans Pro in headings and figures; it has the Vietnamese set too.
// JetBrains Mono sets times, codes and measurements.
const sans = Sarabun({ subsets: ["latin", "vietnamese"], weight: ["400", "500", "600", "700"], variable: "--font-sans", display: "swap" });
const display = Be_Vietnam_Pro({ subsets: ["latin", "vietnamese"], weight: ["500", "600", "700"], variable: "--font-display", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "AI Safety & Compliance Monitoring · Viettel IDC",
  description: "Factory safety monitoring proof of concept",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <body className="font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
