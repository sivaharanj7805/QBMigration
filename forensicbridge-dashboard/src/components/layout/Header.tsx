"use client";

import { useState } from "react";
import { Search, Bell, Cloud, CheckCircle, AlertCircle, User } from "lucide-react";

export function Header() {
    const [searchQuery, setSearchQuery] = useState("");

    return (
        <header className="h-16 bg-white border-b border-[var(--border)] px-6 flex items-center justify-between">
            {/* Search Bar */}
            <div className="flex-1 max-w-md">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search by Session ID or Company Name..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 text-sm border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)] focus:border-transparent"
                    />
                </div>
            </div>

            {/* Right Section */}
            <div className="flex items-center gap-4">
                {/* System Health Status */}
                <SystemHealthBadge />

                {/* Notifications */}
                <button className="relative p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
                    <Bell className="w-5 h-5" />
                    <span className="absolute top-1 right-1 w-2 h-2 bg-[var(--forensic-gold)] rounded-full" />
                </button>

                {/* User Profile */}
                <div className="flex items-center gap-3 pl-4 border-l border-[var(--border)]">
                    <div className="text-right">
                        <p className="text-sm font-medium text-gray-900">CPA Partner</p>
                        <p className="text-xs text-gray-500">Enterprise Account</p>
                    </div>
                    <div className="w-9 h-9 bg-gradient-to-br from-[var(--bridge-blue)] to-[var(--navy-800)] rounded-full flex items-center justify-center">
                        <User className="w-5 h-5 text-white" />
                    </div>
                </div>
            </div>
        </header>
    );
}

function SystemHealthBadge() {
    // In production, this would poll /api/health
    const isHealthy = true;
    const awsConnected = true;

    return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 rounded-lg border border-[var(--border)]">
            <Cloud className={`w-4 h-4 ${awsConnected ? "text-[var(--success)]" : "text-gray-400"}`} />
            <span className="text-xs font-medium text-gray-600">AWS</span>
            {isHealthy ? (
                <CheckCircle className="w-4 h-4 text-[var(--success)]" />
            ) : (
                <AlertCircle className="w-4 h-4 text-[var(--error)]" />
            )}
            <span className={`text-xs font-medium ${isHealthy ? "text-[var(--success)]" : "text-[var(--error)]"}`}>
                {isHealthy ? "Healthy" : "Degraded"}
            </span>
        </div>
    );
}
