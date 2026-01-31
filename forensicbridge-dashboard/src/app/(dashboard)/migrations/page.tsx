"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
    FileSpreadsheet,
    Clock,
    CheckCircle2,
    AlertCircle,
    Search,
    ArrowUpRight,
    Calendar,
    Timer,
    Loader2,
    Play,
    XCircle,
    RefreshCw,
} from "lucide-react";

// MED-36 to MED-40 FIX: Add proper type definitions instead of using 'any'
interface Migration {
    migration_id: string;
    company_name: string;
    qb_file_name?: string;
    records_processed?: number;
    created_at: string;
    status: string;
    progress_percent?: number;
    integrity_verified?: boolean;
}

export default function MigrationsPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const queryClient = useQueryClient();

    const handleCancelMigration = async (migrationId: string) => {
        if (!confirm("Are you sure you want to cancel this migration?")) return;
        setActionLoading(migrationId);
        try {
            const result = await api.cancelMigration(migrationId);
            if (result.success) {
                queryClient.invalidateQueries({ queryKey: ["migrations"] });
            } else {
                alert(result.error || "Failed to cancel migration");
            }
        } catch (error) {
            console.error("Cancel error:", error);
            alert("Failed to cancel migration");
        } finally {
            setActionLoading(null);
        }
    };

    const handleRetryMigration = async (migrationId: string) => {
        setActionLoading(migrationId);
        try {
            const result = await api.retryMigration(migrationId);
            if (result.success) {
                queryClient.invalidateQueries({ queryKey: ["migrations"] });
            } else {
                alert(result.error || "Failed to retry migration");
            }
        } catch (error) {
            console.error("Retry error:", error);
            alert("Failed to retry migration");
        } finally {
            setActionLoading(null);
        }
    };

    // Real Backend Connection
    const { data, isLoading } = useQuery({
        queryKey: ["migrations"],
        queryFn: async () => {
            const response = await api.getMigrations();
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch migrations");
            }
            return response.data;
        }
    });

    const migrations = data?.migrations || [];

    // MED-36 FIX: Use proper typed filter
    const filteredMigrations = migrations.filter((m: Migration) => {
        const matchesSearch = (m.company_name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
            (m.migration_id || "").toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = statusFilter === "all" || m.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    const getStatusBadge = (status: string, progress?: number) => {
        switch (status) {
            case "completed":
                return <span className="badge badge-success"><CheckCircle2 className="w-3 h-3 mr-1" />Completed</span>;
            case "processing":
            case "in_progress":
                return (
                    <span className="badge badge-info flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        {progress || 0}%
                    </span>
                );
            case "failed":
                return <span className="badge badge-error"><AlertCircle className="w-3 h-3 mr-1" />Failed</span>;
            default:
                return <span className="badge badge-gray">{status}</span>;
        }
    };

    // MED-36 FIX: Use proper typed filters
    const completedCount = migrations.filter((m: Migration) => m.status === "completed").length;
    const processingCount = migrations.filter((m: Migration) => m.status === "processing" || m.status === "in_progress").length;
    const failedCount = migrations.filter((m: Migration) => m.status === "failed").length;

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-[var(--bridge-blue)]" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Migrations</h1>
                <p className="text-gray-500 mt-1">View and manage all migration jobs</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{migrations.length}</p>
                            <p className="stat-card-label">Total Migrations</p>
                        </div>
                        <div className="stat-card-icon bg-blue-50 text-blue-600">
                            <FileSpreadsheet className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{completedCount}</p>
                            <p className="stat-card-label">Completed</p>
                        </div>
                        <div className="stat-card-icon bg-green-50 text-green-600">
                            <CheckCircle2 className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{processingCount}</p>
                            <p className="stat-card-label">In Progress</p>
                        </div>
                        <div className="stat-card-icon bg-yellow-50 text-yellow-600">
                            <Clock className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{failedCount}</p>
                            <p className="stat-card-label">Failed</p>
                        </div>
                        <div className="stat-card-icon bg-red-50 text-red-600">
                            <AlertCircle className="w-5 h-5" />
                        </div>
                    </div>
                </div>
            </div>

            {/* Search and Filter */}
            <div className="flex items-center gap-4">
                <div className="flex-1 relative">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search migrations..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="input pl-10"
                    />
                </div>
                <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="input w-40"
                >
                    <option value="all">All Status</option>
                    <option value="completed">Completed</option>
                    <option value="processing">In Progress</option>
                    <option value="failed">Failed</option>
                </select>
            </div>

            {/* Migrations Table */}
            <div className="card-forensic">
                <table className="table-forensic">
                    <thead>
                        <tr>
                            <th>Migration ID</th>
                            <th>Company</th>
                            <th>Records</th>
                            <th>Started</th>
                            <th>Status</th>
                            <th>Verified</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredMigrations.map((migration: Migration) => (
                            <tr key={migration.migration_id}>
                                <td>
                                    <code className="text-[var(--bridge-blue)] text-sm">{migration.migration_id}</code>
                                </td>
                                <td>
                                    <div>
                                        <p className="font-medium text-gray-900">{migration.company_name}</p>
                                        <p className="text-xs text-gray-500">{migration.qb_file_name}</p>
                                    </div>
                                </td>
                                <td className="tabular-nums">{(migration.records_processed || 0).toLocaleString()}</td>
                                <td>
                                    <span className="text-gray-500 flex items-center gap-1 text-sm">
                                        <Calendar className="w-3 h-3" />
                                        {new Date(migration.created_at).toLocaleDateString()}
                                    </span>
                                </td>
                                <td>{getStatusBadge(migration.status, migration.progress_percent)}</td>
                                <td>
                                    {migration.integrity_verified ? (
                                        <span className="text-green-600">✓ Verified</span>
                                    ) : (
                                        <span className="text-gray-400">—</span>
                                    )}
                                </td>
                                <td>
                                    <div className="flex items-center gap-2">
                                        <Link
                                            href={`/migrations/${migration.migration_id}`}
                                            className="btn-secondary text-sm py-1.5 flex items-center gap-1"
                                        >
                                            View <ArrowUpRight className="w-3 h-3" />
                                        </Link>
                                        {(migration.status === "processing" || migration.status === "in_progress") && (
                                            <button
                                                className="text-sm py-1.5 px-2 text-red-600 hover:bg-red-50 rounded flex items-center gap-1"
                                                onClick={() => handleCancelMigration(migration.migration_id)}
                                                disabled={actionLoading === migration.migration_id}
                                            >
                                                <XCircle className="w-3 h-3" />
                                                Cancel
                                            </button>
                                        )}
                                        {migration.status === "failed" && (
                                            <button
                                                className="text-sm py-1.5 px-2 text-blue-600 hover:bg-blue-50 rounded flex items-center gap-1"
                                                onClick={() => handleRetryMigration(migration.migration_id)}
                                                disabled={actionLoading === migration.migration_id}
                                            >
                                                <RefreshCw className="w-3 h-3" />
                                                Retry
                                            </button>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
