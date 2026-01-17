import { Sidebar } from "@/components/layout/Sidebar";
import Providers from "../providers";

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body className="flex h-screen overflow-hidden">
                <Providers>
                    {/* Sidebar */}
                    <Sidebar />

                    {/* Main Content */}
                    <div className="flex-1 flex flex-col overflow-hidden">
                        {/* Header */}
                        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
                            <div className="flex items-center gap-4">
                                <h2 className="text-sm text-gray-500">Enterprise Migration Suite</h2>
                            </div>
                            <div className="flex items-center gap-4">
                                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                                    ✓ All Systems Operational
                                </span>
                                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                                    🍁 ca-central-1
                                </span>
                            </div>
                        </header>

                        {/* Page Content */}
                        <main className="flex-1 overflow-auto bg-gray-50 p-6">
                            {children}
                        </main>
                    </div>
                </Providers>
            </body>
        </html>
    );
}
