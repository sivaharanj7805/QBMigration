import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { QueryProvider } from "@/lib/providers/QueryProvider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

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
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased`}>
        <QueryProvider>
          <div className="flex h-screen overflow-hidden">
            {/* Sidebar */}
            <Sidebar />
            
            {/* Main Content Area */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Top Header */}
              <Header />
              
              {/* Page Content */}
              <main className="flex-1 overflow-auto p-6 bg-[var(--background)]">
                {children}
              </main>
            </div>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
