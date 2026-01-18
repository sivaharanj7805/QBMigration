"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
    LayoutDashboard,
    Upload,
    FolderKanban,
    FileSpreadsheet,
    Database,
    Settings,
    LogOut,
    ChevronLeft,
    ExternalLink
} from "lucide-react";
import { useState } from "react";

const navigation = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Upload", href: "/upload", icon: Upload },
    { name: "Company Files", href: "/projects", icon: FolderKanban },
    { name: "Migrations", href: "/migrations", icon: FileSpreadsheet },
    { name: "Reports", href: "/reports", icon: FileSpreadsheet },
    { name: "Data Museum", href: "/vault", icon: Database },
];

const bottomNav = [
    { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);

    return (
        <aside className={`flex flex-col h-screen bg-white border-r border-gray-200 transition-all duration-300 ${collapsed ? "w-20" : "w-64"
            }`}>
            {/* Logo */}
            <div className="flex items-center justify-between h-20 px-3 border-b border-gray-100">
                {collapsed ? (
                    <div className="flex items-center justify-center w-full">
                        <Image
                            src="/new-logo.png"
                            alt="ForensicBridge"
                            width={48}
                            height={48}
                            className="rounded-lg object-contain"
                        />
                    </div>
                ) : (
                    <div className="flex items-center gap-3">
                        <Image
                            src="/new-logo.png"
                            alt="ForensicBridge"
                            width={56}
                            height={56}
                            className="rounded-lg object-contain"
                        />
                        <div className="flex flex-col">
                            <span className="font-bold text-gray-900 text-sm">ForensicBridge</span>
                            <a
                                href="https://forensicbridge.ca"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-[var(--forensic-gold)] hover:underline flex items-center gap-1"
                            >
                                forensicbridge.ca
                                <ExternalLink className="w-3 h-3" />
                            </a>
                        </div>
                    </div>
                )}
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors flex-shrink-0"
                >
                    <ChevronLeft className={`w-5 h-5 text-gray-400 transition-transform ${collapsed ? "rotate-180" : ""}`} />
                </button>
            </div>

            {/* Main Navigation */}
            <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
                {navigation.map((item) => {
                    const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            className={`sidebar-link ${isActive ? "active" : ""}`}
                            title={collapsed ? item.name : undefined}
                        >
                            <item.icon className="w-5 h-5 flex-shrink-0" />
                            {!collapsed && <span>{item.name}</span>}
                        </Link>
                    );
                })}
            </nav>

            {/* Bottom Navigation */}
            <div className="px-2 py-4 border-t border-gray-100 space-y-1">
                {bottomNav.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            className={`sidebar-link ${isActive ? "active" : ""}`}
                            title={collapsed ? item.name : undefined}
                        >
                            <item.icon className="w-5 h-5 flex-shrink-0" />
                            {!collapsed && <span>{item.name}</span>}
                        </Link>
                    );
                })}
                <button className="sidebar-link w-full text-red-500 hover:bg-red-50">
                    <LogOut className="w-5 h-5 flex-shrink-0" />
                    {!collapsed && <span>Logout</span>}
                </button>
            </div>

            {/* User Info */}
            {!collapsed && (
                <div className="px-4 py-3 border-t border-gray-100">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
                            <span className="text-sm font-medium text-gray-600">JS</span>
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">John Smith</p>
                            <p className="text-xs text-gray-500 truncate">Enterprise Plan</p>
                        </div>
                    </div>
                </div>
            )}
        </aside>
    );
}
