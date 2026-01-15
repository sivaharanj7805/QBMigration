"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    LayoutDashboard,
    Users,
    Archive,
    Settings,
    Shield,
    Database,
    FileCheck,
    Activity,
} from "lucide-react";

const navigation = [
    {
        name: "Dashboard",
        href: "/",
        icon: LayoutDashboard,
        description: "Migration overview",
    },
    {
        name: "Migrations",
        href: "/migrations",
        icon: Database,
        description: "Bulk manager",
    },
    {
        name: "Client Library",
        href: "/clients",
        icon: Users,
        description: "CPA client directory",
    },
    {
        name: "Forensic Vault",
        href: "/vault",
        icon: Archive,
        description: "Certificates & logs",
    },
    {
        name: "Reports",
        href: "/reports",
        icon: FileCheck,
        description: "Audit reports",
    },
];

const bottomNavigation = [
    {
        name: "System Health",
        href: "/health",
        icon: Activity,
    },
    {
        name: "Settings",
        href: "/settings",
        icon: Settings,
    },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="sidebar w-64 flex flex-col h-full">
            {/* Logo */}
            <div className="px-6 py-6 border-b border-white/10">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--forensic-gold)] to-[var(--bridge-blue)] flex items-center justify-center">
                        <Shield className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h1 className="text-lg font-bold text-white">ForensicBridge</h1>
                        <p className="text-xs text-gray-400">Enterprise Migration</p>
                    </div>
                </div>
            </div>

            {/* Main Navigation */}
            <nav className="flex-1 px-3 py-4 space-y-1">
                <p className="px-4 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                    Command Center
                </p>
                {navigation.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            className={`sidebar-link ${isActive ? "active" : ""}`}
                        >
                            <item.icon className="w-5 h-5" />
                            <div>
                                <span className="block">{item.name}</span>
                                <span className="text-xs opacity-60">{item.description}</span>
                            </div>
                        </Link>
                    );
                })}
            </nav>

            {/* Bottom Navigation */}
            <div className="px-3 py-4 border-t border-white/10">
                {bottomNavigation.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            className={`sidebar-link ${isActive ? "active" : ""}`}
                        >
                            <item.icon className="w-5 h-5" />
                            <span>{item.name}</span>
                        </Link>
                    );
                })}
            </div>

            {/* Version */}
            <div className="px-6 py-4 text-xs text-gray-500">
                <p>Version 2.0.0</p>
                <p className="text-gray-600">© 2026 ForensicBridge</p>
            </div>
        </aside>
    );
}
