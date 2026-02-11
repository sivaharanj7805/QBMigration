"use client";

import { useState, useMemo, useCallback } from "react";
import Link from "next/link";
import {
    Play,
    XCircle,
    RotateCcw,
    Eye,
    MoreHorizontal,
    CheckCircle,
    Loader2,
    AlertCircle,
    Clock,
    Upload,
    ChevronUp,
    ChevronDown,
} from "lucide-react";
import { sanitize } from "@/lib/sanitize";

interface Migration {
    id: number;
    migration_id: string;
    status: string;
    company_name: string;
    qb_file_name: string;
    progress_percent: number;
    file_size?: number | null;
    created_at: string;
    completed_at: string | null;
    current_step?: string | null;
}

interface MigrationsTableProps {
    migrations: Migration[];
    onStart?: (id: string) => void;
    onCancel?: (id: string) => void;
    onRetry?: (id: string) => void;
    onDelete?: (id: string) => void;
    isLoading?: boolean;
    selectedIds?: Set<string>;
    onSelectionChange?: (ids: Set<string>) => void;
    // FIX: Add error state to distinguish from empty state
    error?: string | null;
}

type SortField = "company_name" | "status" | "progress_percent" | "created_at";
type SortOrder = "asc" | "desc";

export function MigrationsTable({
    migrations,
    onStart,
    onCancel,
    onRetry,
    onDelete,
    isLoading,
    selectedIds = new Set(),
    onSelectionChange,
    error,
}: MigrationsTableProps) {
    const [sortField, setSortField] = useState<SortField>("created_at");
    const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
    // FIX FE-02: Add state for More Options dropdown
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);

    const handleSort = useCallback((field: SortField) => {
        if (sortField === field) {
            setSortOrder(sortOrder === "asc" ? "desc" : "asc");
        } else {
            setSortField(field);
            setSortOrder("asc");
        }
    }, [sortField, sortOrder]);

    // FIX FE-03: Memoize sorted migrations to prevent unnecessary re-sorting
    const sortedMigrations = useMemo(() => {
        return [...migrations].sort((a, b) => {
            let aVal: string | number = a[sortField];
            let bVal: string | number = b[sortField];

            if (sortField === "created_at") {
                aVal = new Date(aVal as string).getTime();
                bVal = new Date(bVal as string).getTime();
            }

            if (aVal < bVal) return sortOrder === "asc" ? -1 : 1;
            if (aVal > bVal) return sortOrder === "asc" ? 1 : -1;
            return 0;
        });
    }, [migrations, sortField, sortOrder]);

    const toggleSelection = (id: string) => {
        const newSelection = new Set(selectedIds);
        if (newSelection.has(id)) {
            newSelection.delete(id);
        } else {
            newSelection.add(id);
        }
        onSelectionChange?.(newSelection);
    };

    const toggleAll = () => {
        if (selectedIds.size === migrations.length) {
            onSelectionChange?.(new Set());
        } else {
            onSelectionChange?.(new Set(migrations.map((m) => m.migration_id)));
        }
    };

    const formatFileSize = (bytes: number | null | undefined) => {
        if (!bytes) return "—";
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
        return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    };

    const formatTimeAgo = (dateStr: string) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now.getTime() - date.getTime();
        const mins = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (mins < 1) return "Just now";
        if (mins < 60) return `${mins} min ago`;
        if (hours < 24) return `${hours}h ago`;
        return `${days}d ago`;
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "completed":
                return (
                    <span className="badge-success flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" /> Completed
                    </span>
                );
            case "processing":
                return (
                    <span className="badge-processing flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" /> Processing
                    </span>
                );
            case "failed":
                return (
                    <span className="badge-error flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" /> Failed
                    </span>
                );
            case "uploaded":
                return (
                    <span className="badge-warning flex items-center gap-1">
                        <Upload className="w-3 h-3" /> Ready
                    </span>
                );
            case "pending":
                return (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                        <Clock className="w-3 h-3" /> Pending
                    </span>
                );
            default:
                return (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                        {status}
                    </span>
                );
        }
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return null;
        return sortOrder === "asc" ? (
            <ChevronUp className="w-4 h-4" />
        ) : (
            <ChevronDown className="w-4 h-4" />
        );
    };

    // FIX: Add loading skeleton for better UX
    if (isLoading) {
        return (
            <div className="card-forensic overflow-hidden">
                <table className="data-table">
                    <thead>
                        <tr>
                            <th className="w-12"><div className="h-4 w-4 bg-gray-200 rounded animate-pulse" /></th>
                            <th>Client Name</th>
                            <th>File Size</th>
                            <th>Last Sync</th>
                            <th>Status</th>
                            <th>Progress</th>
                            <th className="text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {[1, 2, 3].map((i) => (
                            <tr key={i}>
                                <td><div className="h-4 w-4 bg-gray-200 rounded animate-pulse" /></td>
                                <td>
                                    <div className="h-4 w-32 bg-gray-200 rounded animate-pulse mb-1" />
                                    <div className="h-3 w-24 bg-gray-100 rounded animate-pulse" />
                                </td>
                                <td><div className="h-4 w-16 bg-gray-200 rounded animate-pulse" /></td>
                                <td><div className="h-4 w-16 bg-gray-200 rounded animate-pulse" /></td>
                                <td><div className="h-6 w-20 bg-gray-200 rounded-full animate-pulse" /></td>
                                <td><div className="h-2 w-20 bg-gray-200 rounded animate-pulse" /></td>
                                <td><div className="h-6 w-6 bg-gray-200 rounded animate-pulse ml-auto" /></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    // FIX: Show error state if error is provided
    if (error) {
        return (
            <div className="card-forensic overflow-hidden">
                <div className="p-8 text-center">
                    <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
                    <p className="text-lg font-medium text-gray-900">Failed to load migrations</p>
                    <p className="mt-1 text-gray-500">{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="card-forensic overflow-hidden">
            <table className="data-table">
                <thead>
                    <tr>
                        <th className="w-12">
                            <input
                                type="checkbox"
                                checked={selectedIds.size === migrations.length && migrations.length > 0}
                                onChange={toggleAll}
                                className="rounded border-gray-300"
                            />
                        </th>
                        <th
                            className="cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort("company_name")}
                        >
                            <div className="flex items-center gap-1">
                                Client Name <SortIcon field="company_name" />
                            </div>
                        </th>
                        <th>File Size</th>
                        <th
                            className="cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort("created_at")}
                        >
                            <div className="flex items-center gap-1">
                                Last Sync <SortIcon field="created_at" />
                            </div>
                        </th>
                        <th
                            className="cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort("status")}
                        >
                            <div className="flex items-center gap-1">
                                Status <SortIcon field="status" />
                            </div>
                        </th>
                        <th
                            className="cursor-pointer hover:bg-gray-100"
                            onClick={() => handleSort("progress_percent")}
                        >
                            <div className="flex items-center gap-1">
                                Progress <SortIcon field="progress_percent" />
                            </div>
                        </th>
                        <th className="text-right">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {sortedMigrations.length === 0 ? (
                        <tr>
                            <td colSpan={7} className="text-center py-8">
                                {/* FIX: Better empty state with helpful message */}
                                <Upload className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                                <p className="text-lg font-medium text-gray-600">No migrations yet</p>
                                <p className="text-gray-400 text-sm mt-1">Upload a QuickBooks file to get started</p>
                            </td>
                        </tr>
                    ) : (
                        sortedMigrations.map((migration) => (
                            <tr key={migration.migration_id}>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={selectedIds.has(migration.migration_id)}
                                        onChange={() => toggleSelection(migration.migration_id)}
                                        className="rounded border-gray-300"
                                    />
                                </td>
                                <td>
                                    <Link
                                        href={`/migrations/${migration.migration_id}`}
                                        className="font-medium text-gray-900 hover:text-[var(--bridge-blue)]"
                                    >
                                        {sanitize.text(migration.company_name)}
                                    </Link>
                                    <p className="text-xs text-gray-500">{sanitize.text(migration.qb_file_name)}</p>
                                </td>
                                <td className="tabular-nums">{formatFileSize(migration.file_size)}</td>
                                <td className="text-gray-500">{formatTimeAgo(migration.created_at)}</td>
                                <td>{getStatusBadge(migration.status)}</td>
                                <td>
                                    <div className="flex items-center gap-2">
                                        {/* FIX: Added ARIA attributes for accessibility */}
                                        <div
                                            className="progress-bar w-20"
                                            role="progressbar"
                                            aria-valuenow={migration.progress_percent}
                                            aria-valuemin={0}
                                            aria-valuemax={100}
                                            aria-label={`${migration.company_name} migration progress: ${migration.progress_percent}%`}
                                        >
                                            <div
                                                className={`progress-bar-fill ${migration.status === "completed" ? "success" : ""
                                                    }`}
                                                style={{ width: `${migration.progress_percent}%` }}
                                            />
                                        </div>
                                        <span className="text-xs text-gray-500 tabular-nums w-10">
                                            {migration.progress_percent}%
                                        </span>
                                    </div>
                                </td>
                                <td>
                                    <div className="flex items-center justify-end gap-1">
                                        <Link
                                            href={`/migrations/${migration.migration_id}`}
                                            className="p-1.5 hover:bg-gray-100 rounded transition-colors"
                                            title="View Details"
                                        >
                                            <Eye className="w-4 h-4 text-gray-500" />
                                        </Link>
                                        {migration.status === "uploaded" && onStart && (
                                            <button
                                                onClick={() => onStart(migration.migration_id)}
                                                className="p-1.5 hover:bg-green-50 rounded transition-colors"
                                                title="Start Migration"
                                            >
                                                <Play className="w-4 h-4 text-[var(--success)]" />
                                            </button>
                                        )}
                                        {migration.status === "processing" && onCancel && (
                                            <button
                                                onClick={() => onCancel(migration.migration_id)}
                                                className="p-1.5 hover:bg-red-50 rounded transition-colors"
                                                title="Cancel Migration"
                                            >
                                                <XCircle className="w-4 h-4 text-[var(--error)]" />
                                            </button>
                                        )}
                                        {migration.status === "failed" && onRetry && (
                                            <button
                                                onClick={() => onRetry(migration.migration_id)}
                                                className="p-1.5 hover:bg-blue-50 rounded transition-colors"
                                                title="Retry Migration"
                                            >
                                                <RotateCcw className="w-4 h-4 text-[var(--bridge-blue)]" />
                                            </button>
                                        )}
                                        {/* FIX FE-02: More Options dropdown with actual functionality */}
                                        <div className="relative">
                                            <button
                                                className="p-1.5 hover:bg-gray-100 rounded transition-colors"
                                                title="More Options"
                                                onClick={() => setOpenMenuId(
                                                    openMenuId === migration.migration_id ? null : migration.migration_id
                                                )}
                                            >
                                                <MoreHorizontal className="w-4 h-4 text-gray-400" />
                                            </button>
                                            {openMenuId === migration.migration_id && (
                                                <div className="absolute right-0 mt-1 w-48 bg-white rounded-md shadow-lg z-10 border border-gray-200">
                                                    <div className="py-1">
                                                        <Link
                                                            href={`/migrations/${migration.migration_id}`}
                                                            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                            onClick={() => setOpenMenuId(null)}
                                                        >
                                                            View Details
                                                        </Link>
                                                        <Link
                                                            href={`/migrations/${migration.migration_id}/audit`}
                                                            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                            onClick={() => setOpenMenuId(null)}
                                                        >
                                                            View Audit Log
                                                        </Link>
                                                        <Link
                                                            href={`/migrations/${migration.migration_id}/certificate`}
                                                            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                            onClick={() => setOpenMenuId(null)}
                                                        >
                                                            Download Certificate
                                                        </Link>
                                                        <hr className="my-1 border-gray-200" />
                                                        <button
                                                            className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
                                                            onClick={() => {
                                                                setOpenMenuId(null);
                                                                if (onDelete) {
                                                                    onDelete(migration.migration_id);
                                                                }
                                                            }}
                                                            disabled={!onDelete}
                                                        >
                                                            Delete Migration
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}
