import "./globals.css";
import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import Providers from "@/components/providers";

// Plus Jakarta Sans is the only face on madison-technologies.com, for body text and headings alike.
// It carries every user-entered name (full Vietnamese subset). JetBrains Mono sets times, codes and measurements.
const sans = Plus_Jakarta_Sans({ subsets: ["latin", "vietnamese"], weight: ["400", "500", "600", "700"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "AI Safety & Compliance Monitoring · Madison Technologies",
  description: "Factory safety monitoring proof of concept",
};

// cover lets the phone tab bar pad itself past the home indicator; the theme colour matches the navy top bar.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0A1525",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
