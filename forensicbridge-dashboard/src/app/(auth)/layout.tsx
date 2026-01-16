import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "../globals.css";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-inter",
});

export const metadata: Metadata = {
    title: "ForensicBridge | Sign In",
    description: "Sign in to ForensicBridge - Secure QuickBooks Migration",
};

export default function AuthLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <body className={`${inter.variable} font-sans antialiased`}>
                {/* Auth pages have their own full-screen layout - no sidebar or header */}
                {children}
            </body>
        </html>
    );
}
