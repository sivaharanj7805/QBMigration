import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ForensicBridge | Enterprise Migration Command Center",
  description: "The Institutional Standard for Financial Data Integrity. Secure, verified QuickBooks migrations with SHA-256 chain of custody.",
  keywords: ["QuickBooks", "Migration", "QBO", "Accounting", "Data Integrity", "Forensic"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // This is just a pass-through - route groups handle their own layouts
  return children;
}
