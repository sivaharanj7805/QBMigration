"use client";

import { useState, useCallback, useEffect, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useDebouncedValue, useLoadingGuard } from "@/lib/hooks/useSecurityHooks";
import { sanitize } from "@/lib/sanitize";
import {
    FileSpreadsheet,
    Clock,
    CheckCircle2,
    AlertCircle,
    Search,
    ArrowUpRight,
    Calendar,
    Loader2,
    XCircle,
    RefreshCw,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";

// Proper TypeScript interfaces instead of 'any'
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

interface MigrationStats {
    total: number;
    completed: number;
    processing: number;
    failed: number;
}

// Pagination component
function Pagination({
    currentPage,
    totalPages,
    onPageChange,
    disabled,
}: {
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
    disabled?: boolean;
}) {
    const pages = [];
    const maxVisiblePages = 5;

    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    const endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        pages.push(i);
    }

    return (
        <div className="flex items-center justify-between px-4 py-3 bg-white border-t border-gray-200">
            <div className="text-sm text-gray-500">
                Page {currentPage} of {totalPages}
            </div>
            <div className="flex items-center gap-1">
                <button
                    onClick={() => onPageChange(currentPage - 1)}
                    disabled={currentPage <= 1 || disabled}
                    className="p-2 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Previous page"
                >
                    <ChevronLeft className="w-4 h-4" />
                </button>

                {startPage > 1 && (
                    <>
                        <button
                            onClick={() => onPageChange(1)}
                            disabled={disabled}
                            className="px-3 py-1 rounded hover:bg-gray-100"
                        >
                            1
                        </button>
                        {startPage > 2 && <span className="px-2 text-gray-400">...</span>}
                    </>
                )}

                {pages.map((page) => (
                    <button
                        key={page}
                        onClick={() => onPageChange(page)}
                        disabled={disabled}
                        className={`px-3 py-1 rounded ${
                            page === currentPage
                                ? "bg-blue-600 text-white"
                                : "hover:bg-gray-100"
                        }`}
                    >
                        {page}
                    </button>
                ))}

                {endPage < totalPages && (
                    <>
                        {endPage < totalPages - 1 && <span className="px-2 text-gray-400">...</span>}
                        <button
                            onClick={() => onPageChange(totalPages)}
                            disabled={disabled}
                            className="px-3 py-1 rounded hover:bg-gray-100"
                        >
                            {totalPages}
                        </button>
                    </>
                )}

                <button
                    onClick={() => onPageChange(currentPage + 1)}
                    disabled={currentPage >= totalPages || disabled}
                    className="p-2 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Next page"
                >
                    <ChevronRight className="w-4 h-4" />
                </button>
            </div>
        </div>
    );
}

// Stats card component
function StatsCard({
    value,
    label,
    icon: Icon,
    iconBgColor,
    iconColor,
}: {
    value: number;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    iconBgColor: string;
    iconColor: string;
}) {
    return (
        <div className="stat-card">
            <div className="flex items-start justify-between">
                <div>
                    <p className="stat-card-value">{value}</p>
                    <p className="stat-card-label">{label}</p>
                </div>
                <div className={`stat-card-icon ${iconBgColor} ${iconColor}`}>
                    <Icon className="w-5 h-5" />
                </div>
            </div>
        </div>
    );
}

// Status badge component
function StatusBadge({ status, progress }: { status: string; progress?: number }) {
    switch (status) {
        case "completed":
            return (
                <span className="badge badge-success">
                    <CheckCircle2 className="w-3 h-3 mr-1" />
                    Completed
                </span>
            );
        case "processing":
        case "in_progress":
            return (
                <span className="badge badge-info flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {progress || 0}%
                </span>
            );
        case "failed":
            return (
                <span className="badge badge-error">
                    <AlertCircle className="w-3 h-3 mr-1" />
                    Failed
                </span>
            );
        default:
            return <span className="badge badge-gray">{status}</span>;
    }
}

// Migration row component
function MigrationRow({
    migration,
    onCancel,
    onRetry,
    isActionLoading,
}: {
    migration: Migration;
    onCancel: (id: string) => void;
    onRetry: (id: string) => void;
    isActionLoading: boolean;
}) {
    const isProcessing = migration.status === "processing" || migration.status === "in_progress";
    const isFailed = migration.status === "failed";

    return (
        <tr>
            <td>
                <code className="text-[var(--bridge-blue)] text-sm">
                    {sanitize.text(migration.migration_id)}
                </code>
            </td>
            <td>
                <div>
                    <p className="font-medium text-gray-900">
                        {sanitize.text(migration.company_name)}
                    </p>
                    <p className="text-xs text-gray-500">
                        {sanitize.text(migration.qb_file_name || '')}
                    </p>
                </div>
            </td>
            <td className="tabular-nums">
                {(migration.records_processed || 0).toLocaleString()}
            </td>
            <td>
                <span className="text-gray-500 flex items-center gap-1 text-sm">
                    <Calendar className="w-3 h-3" />
                    {new Date(migration.created_at).toLocaleDateString()}
                </span>
            </td>
            <td>
                <StatusBadge status={migration.status} progress={migration.progress_percent} />
            </td>
            <td>
                {migration.integrity_verified ? (
                    <span className="text-green-600">Verified</span>
                ) : (
                    <span className="text-gray-400">-</span>
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
                    {isProcessing && (
                        <button
                            className="text-sm py-1.5 px-2 text-red-600 hover:bg-red-50 rounded flex items-center gap-1 disabled:opacity-50"
                            onClick={() => onCancel(migration.migration_id)}
                            disabled={isActionLoading}
                        >
                            <XCircle className="w-3 h-3" />
                            Cancel
                        </button>
                    )}
                    {isFailed && (
                        <button
                            className="text-sm py-1.5 px-2 text-blue-600 hover:bg-blue-50 rounded flex items-center gap-1 disabled:opacity-50"
                            onClick={() => onRetry(migration.migration_id)}
                            disabled={isActionLoading}
                        >
                            <RefreshCw className="w-3 h-3" />
                            Retry
                        </button>
                    )}
                </div>
            </td>
        </tr>
    );
}

export default function MigrationsPage() {
    // Search with debouncing
    const [searchTerm, setSearchTerm] = useState("");
    const debouncedSearchTerm = useDebouncedValue(searchTerm, 300);

    // Filters and pagination
    const [statusFilter, setStatusFilter] = useState("all");
    const [currentPage, setCurrentPage] = useState(1);
    const [perPage] = useState(20);

    // Loading guard for actions (prevents race conditions/double-clicks)
    const { isLoading: isActionLoading, execute } = useLoadingGuard();

    // Error state
    const [actionError, setActionError] = useState<string | null>(null);

    const queryClient = useQueryClient();

    // Reset to page 1 when filters change
    useEffect(() => {
        setCurrentPage(1);
    }, [debouncedSearchTerm, statusFilter]);

    // Auto-dismiss errors after 5 seconds
    useEffect(() => {
        if (actionError) {
            const timer = setTimeout(() => setActionError(null), 5000);
            return () => clearTimeout(timer);
        }
    }, [actionError]);

    // Cancel migration with loading guard
    const handleCancelMigration = useCallback(async (migrationId: string) => {
        if (!confirm("Are you sure you want to cancel this migration?")) return;

        setActionError(null);
        const result = await execute(async (signal) => {
            return await api.cancelMigration(migrationId, signal);
        });

        if (result) {
            if (result.success) {
                queryClient.invalidateQueries({ queryKey: ["migrations"] });
            } else {
                setActionError(result.error || "Failed to cancel migration");
            }
        }
    }, [execute, queryClient]);

    // Retry migration with loading guard
    const handleRetryMigration = useCallback(async (migrationId: string) => {
        setActionError(null);
        const result = await execute(async (signal) => {
            return await api.retryMigration(migrationId, signal);
        });

        if (result) {
            if (result.success) {
                queryClient.invalidateQueries({ queryKey: ["migrations"] });
            } else {
                setActionError(result.error || "Failed to retry migration");
            }
        }
    }, [execute, queryClient]);

    // Fetch migrations with pagination
    const { data, isLoading, error } = useQuery({
        queryKey: ["migrations", currentPage, perPage],
        queryFn: async ({ signal }) => {
            const response = await api.getMigrations(currentPage, perPage, signal);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch migrations");
            }
            return response.data;
        },
        staleTime: 5000,
    });

    const migrations = data?.migrations || [];
    // FIX F-04: Use pagination.pages from schema (consistent with MigrationListSchema)
    const totalPages = data?.pagination?.pages || data?.total_pages || 1;

    // Client-side filtering (server-side would be better for large datasets)
    const filteredMigrations = migrations.filter((m: Migration) => {
        const searchLower = debouncedSearchTerm.toLowerCase();
        const matchesSearch =
            (m.company_name || "").toLowerCase().includes(searchLower) ||
            (m.migration_id || "").toLowerCase().includes(searchLower);
        const matchesStatus = statusFilter === "all" || m.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    // Calculate stats from API response totals instead of filtered page data
    const stats: MigrationStats = useMemo(() => {
        if (!data) return { total: 0, completed: 0, processing: 0, failed: 0 };
        return {
            total: (data as Record<string, unknown>).total as number || data.count || 0,
            completed: (data as Record<string, unknown>).completed_count as number || migrations.filter((m: Migration) => m.status === "completed").length,
            processing: (data as Record<string, unknown>).processing_count as number || migrations.filter(
                (m: Migration) => m.status === "processing" || m.status === "in_progress" || m.status === "provisioning"
            ).length,
            failed: (data as Record<string, unknown>).failed_count as number || migrations.filter((m: Migration) => m.status === "failed").length,
        };
    }, [data, migrations]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-[var(--bridge-blue)]" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="card-forensic p-8 text-center">
                <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
                <p className="text-lg font-medium text-gray-900">Failed to load migrations</p>
                <p className="mt-1 text-gray-500">
                    {error instanceof Error ? error.message : "Unknown error"}
                </p>
                <button
                    onClick={() => queryClient.invalidateQueries({ queryKey: ["migrations"] })}
                    className="btn-primary mt-4"
                >
                    Try Again
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Error toast for action errors */}
            {actionError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-red-700">
                        <AlertCircle className="w-5 h-5" />
                        {actionError}
                    </div>
                    <button
                        onClick={() => setActionError(null)}
                        className="text-red-500 hover:text-red-700 text-sm"
                    >
                        Dismiss
                    </button>
                </div>
            )}

            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Migrations</h1>
                <p className="text-gray-500 mt-1">View and manage all migration jobs</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <StatsCard
                    value={stats.total}
                    label="Total Migrations"
                    icon={FileSpreadsheet}
                    iconBgColor="bg-blue-50"
                    iconColor="text-blue-600"
                />
                <StatsCard
                    value={stats.completed}
                    label="Completed"
                    icon={CheckCircle2}
                    iconBgColor="bg-green-50"
                    iconColor="text-green-600"
                />
                <StatsCard
                    value={stats.processing}
                    label="In Progress"
                    icon={Clock}
                    iconBgColor="bg-yellow-50"
                    iconColor="text-yellow-600"
                />
                <StatsCard
                    value={stats.failed}
                    label="Failed"
                    icon={AlertCircle}
                    iconBgColor="bg-red-50"
                    iconColor="text-red-600"
                />
            </div>

            {/* Search and Filter */}
            <div className="flex items-center gap-4">
                <div className="flex-1 relative">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search migrations..."
                        value={searchTerm}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchTerm(e.target.value)}
                        className="input pl-10"
                        maxLength={200}
                        aria-label="Search migrations"
                    />
                </div>
                <select
                    value={statusFilter}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setStatusFilter(e.target.value)}
                    className="input w-40"
                    aria-label="Filter by status"
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
                        {filteredMigrations.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="text-center py-8">
                                    <FileSpreadsheet className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                                    <p className="text-lg font-medium text-gray-600">
                                        {debouncedSearchTerm || statusFilter !== "all"
                                            ? "No migrations match your filters"
                                            : "No migrations yet"}
                                    </p>
                                    <p className="text-sm text-gray-400 mt-1">
                                        {debouncedSearchTerm || statusFilter !== "all"
                                            ? "Try adjusting your search or filters"
                                            : "Upload a QuickBooks file to get started"}
                                    </p>
                                </td>
                            </tr>
                        ) : (
                            filteredMigrations.map((migration: Migration) => (
                                <MigrationRow
                                    key={migration.migration_id}
                                    migration={migration}
                                    onCancel={handleCancelMigration}
                                    onRetry={handleRetryMigration}
                                    isActionLoading={isActionLoading}
                                />
                            ))
                        )}
                    </tbody>
                </table>

                {/* Pagination */}
                {totalPages > 1 && (
                    <Pagination
                        currentPage={currentPage}
                        totalPages={totalPages}
                        onPageChange={setCurrentPage}
                        disabled={isLoading}
                    />
                )}
            </div>
        </div>
    );
}
