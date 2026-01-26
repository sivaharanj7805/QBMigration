import type { Metadata } from "next";
import "../globals.css";

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
            <body className="font-sans antialiased">
                {/* Auth pages have their own full-screen layout - no sidebar or header */}
                {children}
            </body>
        </html>
    );
}
