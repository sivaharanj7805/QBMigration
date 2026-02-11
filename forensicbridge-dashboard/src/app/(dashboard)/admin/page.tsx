"use client";

/**
 * Admin Dashboard Page
 *
 * AUDIT FIX MUST-04: Provides a dedicated admin frontend panel for support staff
 * to view tenants, migration health, licenses, and system status without curl commands.
 *
 * Protected by admin role check — non-admin users see an access denied message.
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { getAuthState, authFetch } from "@/lib/auth";
import { sanitize } from "@/lib/sanitize";
import {
    Users,
    Activity,
    AlertTriangle,
    CheckCircle,
    XCircle,
    Clock,
    Shield,
    RefreshCw,
    Search,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface SystemHealth {
    status: string;
    database: string;
    redis: string;
    uptime_seconds: number;
    version: string;
}

interface UserSummary {
    id: number;
    email: string;
    name: string;
    company: string;
    role: string;
    is_active: boolean;
    created_at: string;
    migrations_count: number;
    last_login: string | null;
}

interface MigrationSummary {
    total: number;
    completed: number;
    failed: number;
    in_progress: number;
    pending: number;
}

export default function AdminPage() {
    const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [users, setUsers] = useState<UserSummary[]>([]);
    const [migrationStats, setMigrationStats] = useState<MigrationSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");
    const isMountedRef = useRef(true);

    useEffect(() => {
        return () => { isMountedRef.current = false; };
    }, []);

    // Check admin role
    useEffect(() => {
        const authState = getAuthState();
        const role = authState.user?.role;
        setIsAdmin(role === "admin" || role === "super_admin");
    }, []);

    const fetchAdminData = useCallback(async () => {
        if (!isMountedRef.current) return;
        setLoading(true);
        setError(null);

        try {
            // Fetch system health
            const healthRes = await fetch(`${API_URL}/api/health`);
            if (healthRes.ok && isMountedRef.current) {
                setHealth(await healthRes.json());
            }

            // Fetch admin users list
            const usersRes = await authFetch(`${API_URL}/api/internal/admin/users`);
            if (usersRes.ok && isMountedRef.current) {
                const data = await usersRes.json();
                setUsers(data.users || []);
            }

            // Fetch migration statistics
            const statsRes = await authFetch(`${API_URL}/api/internal/admin/migration-stats`);
            if (statsRes.ok && isMountedRef.current) {
                const data = await statsRes.json();
                setMigrationStats(data.stats || null);
            }
        } catch (err) {
            if (isMountedRef.current) {
                setError("Failed to load admin data. Please check your permissions.");
            }
        } finally {
            if (isMountedRef.current) {
                setLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        if (isAdmin) {
            fetchAdminData();
        }
    }, [isAdmin, fetchAdminData]);

    // Access denied for non-admins
    if (isAdmin === false) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="text-center">
                    <Shield className="w-16 h-16 text-red-400 mx-auto mb-4" />
                    <h2 className="text-xl font-semibold text-gray-900 mb-2">Access Denied</h2>
                    <p className="text-gray-600">You need admin privileges to access this page.</p>
                </div>
            </div>
        );
    }

    // Loading state
    if (isAdmin === null || loading) {
        return (
            <div className="p-6 space-y-6 animate-pulse">
                <div className="h-8 bg-gray-200 rounded w-48" />
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    {[1, 2, 3, 4].map(i => (
                        <div key={i} className="h-32 bg-gray-200 rounded-xl" />
                    ))}
                </div>
                <div className="h-64 bg-gray-200 rounded-xl" />
            </div>
        );
    }

    const filteredUsers = users.filter(u =>
        u.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        u.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        u.company?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
                    <p className="text-sm text-gray-500 mt-1">System health, users, and migration overview</p>
                </div>
                <button
                    onClick={fetchAdminData}
                    className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 text-sm font-medium"
                >
                    <RefreshCw className="w-4 h-4" />
                    Refresh
                </button>
            </div>

            {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
                    {error}
                </div>
            )}

            {/* System Health Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border border-gray-200 p-5">
                    <div className="flex items-center gap-3 mb-3">
                        <Activity className="w-5 h-5 text-green-500" />
                        <span className="text-sm font-medium text-gray-500">System Status</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {health?.status === "healthy" ? (
                            <CheckCircle className="w-5 h-5 text-green-500" />
                        ) : (
                            <AlertTriangle className="w-5 h-5 text-yellow-500" />
                        )}
                        <span className="text-lg font-semibold capitalize">{health?.status || "Unknown"}</span>
                    </div>
                    <p className="text-xs text-gray-400 mt-2">
                        DB: {health?.database || "?"} | Redis: {health?.redis || "?"}
                    </p>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-5">
                    <div className="flex items-center gap-3 mb-3">
                        <Users className="w-5 h-5 text-blue-500" />
                        <span className="text-sm font-medium text-gray-500">Total Users</span>
                    </div>
                    <span className="text-2xl font-bold">{users.length}</span>
                    <p className="text-xs text-gray-400 mt-2">
                        Active: {users.filter(u => u.is_active).length}
                    </p>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-5">
                    <div className="flex items-center gap-3 mb-3">
                        <CheckCircle className="w-5 h-5 text-green-500" />
                        <span className="text-sm font-medium text-gray-500">Migrations Completed</span>
                    </div>
                    <span className="text-2xl font-bold">{migrationStats?.completed ?? 0}</span>
                    <p className="text-xs text-gray-400 mt-2">
                        Total: {migrationStats?.total ?? 0}
                    </p>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-5">
                    <div className="flex items-center gap-3 mb-3">
                        {(migrationStats?.failed ?? 0) > 0 ? (
                            <XCircle className="w-5 h-5 text-red-500" />
                        ) : (
                            <Clock className="w-5 h-5 text-amber-500" />
                        )}
                        <span className="text-sm font-medium text-gray-500">
                            {(migrationStats?.failed ?? 0) > 0 ? "Failed" : "In Progress"}
                        </span>
                    </div>
                    <span className="text-2xl font-bold">
                        {(migrationStats?.failed ?? 0) > 0
                            ? migrationStats?.failed
                            : migrationStats?.in_progress ?? 0}
                    </span>
                    <p className="text-xs text-gray-400 mt-2">
                        Pending: {migrationStats?.pending ?? 0}
                    </p>
                </div>
            </div>

            {/* Users Table */}
            <div className="bg-white rounded-xl border border-gray-200">
                <div className="p-5 border-b border-gray-100 flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-gray-900">Users</h2>
                    <div className="relative">
                        <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                        <input
                            type="text"
                            placeholder="Search users..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            className="pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                            aria-label="Search users by email, name, or company"
                        />
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-gray-100 text-left">
                                <th className="px-5 py-3 font-medium text-gray-500">User</th>
                                <th className="px-5 py-3 font-medium text-gray-500">Company</th>
                                <th className="px-5 py-3 font-medium text-gray-500">Role</th>
                                <th className="px-5 py-3 font-medium text-gray-500">Migrations</th>
                                <th className="px-5 py-3 font-medium text-gray-500">Status</th>
                                <th className="px-5 py-3 font-medium text-gray-500">Last Login</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredUsers.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-5 py-8 text-center text-gray-400">
                                        {searchQuery ? "No users match your search." : "No users found."}
                                    </td>
                                </tr>
                            ) : (
                                filteredUsers.map(user => (
                                    <tr key={user.id} className="border-b border-gray-50 hover:bg-gray-50">
                                        <td className="px-5 py-3">
                                            <div>
                                                <p className="font-medium text-gray-900">{sanitize.text(user.name || "—")}</p>
                                                <p className="text-xs text-gray-400">{sanitize.text(user.email)}</p>
                                            </div>
                                        </td>
                                        <td className="px-5 py-3 text-gray-600">{sanitize.text(user.company || "—")}</td>
                                        <td className="px-5 py-3">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                                user.role === "admin" || user.role === "super_admin"
                                                    ? "bg-purple-100 text-purple-700"
                                                    : "bg-gray-100 text-gray-700"
                                            }`}>
                                                {user.role}
                                            </span>
                                        </td>
                                        <td className="px-5 py-3 text-gray-600">{user.migrations_count ?? 0}</td>
                                        <td className="px-5 py-3">
                                            <span className={`inline-flex items-center gap-1 text-xs font-medium ${
                                                user.is_active ? "text-green-600" : "text-red-500"
                                            }`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${user.is_active ? "bg-green-500" : "bg-red-400"}`} />
                                                {user.is_active ? "Active" : "Inactive"}
                                            </span>
                                        </td>
                                        <td className="px-5 py-3 text-gray-400 text-xs">
                                            {user.last_login
                                                ? new Date(user.last_login).toLocaleDateString()
                                                : "Never"}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
