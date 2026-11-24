import type { Metadata, Viewport } from "next";
import { Inter, Lora } from "next/font/google";

import { AuthProvider } from "@/lib/auth";

import "./globals.css";

const lora = Lora({
  variable: "--font-lora",
  subsets: ["latin"],
  style: ["normal", "italic"], // variable weight; headings use 400
});
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Kira Verbal",
  description: "Voice check-ins for learning (independent prototype, synthetic data only)",
};

export const viewport: Viewport = {
  themeColor: "#fefdf0",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // The font variables go on <html>: Tailwind defines --font-serif/--font-sans on :root as
    // var(--font-lora)/var(--font-inter), and var() resolves where the property is defined.
    // On <body> they would be undefined at :root and every font would fall back to the default.
    <html lang="en" className={`${lora.variable} ${inter.variable}`}>
      <body className="min-h-screen antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
