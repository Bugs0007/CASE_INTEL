import type { Metadata } from "next";
import { Newsreader, Public_Sans, IBM_Plex_Mono } from "next/font/google";
// Design tokens first, ahead of everything else -- Tailwind's own
// base/components/utilities (pulled in by globals.css) and every component
// class that follows derive their colors, radii, and type from these vars.
import "./case-intel-theme.css";
import "./globals.css";
import { QueryProvider } from "@/providers/query-provider";
import { Toaster } from "@/components/ui/toaster";

// Each font's `variable` name is set to the exact CSS custom property
// case-intel-theme.css already declares (--ci-serif/--ci-sans/--ci-mono)
// with a plain fallback stack. Applying these on <body> below makes the
// loaded webfont win over that fallback unconditionally -- body's own
// direct declaration always beats the inherited one from :root, regardless
// of stylesheet order.
const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--ci-serif",
  display: "swap",
});

const publicSans = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--ci-sans",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--ci-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Case Intel - Legal Case Management",
  description: "AI-powered legal case management platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${newsreader.variable} ${publicSans.variable} ${ibmPlexMono.variable}`}>
        <QueryProvider>{children}</QueryProvider>
        <Toaster />
      </body>
    </html>
  );
}
