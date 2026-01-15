"use client";

import { useState } from "react";
import { useMigrations, useStartMigration, useCancelMigration, useRetryMigration } from "@/lib/hooks/useMigrations";
import { MigrationsTable } from "@/components/migrations/MigrationsTable";
import { Search, Filter, Download, Play, XCircle, RefreshCw } from "lucide-react";

export default function MigrationsPage() {
    const { data, isLoading, refetch } = useMigrations();
    const startMutation = useStartMigration();
    const cancelMutation = useCancelMigration();
    const retryMutation = useRetryMigration();

    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

    const migrations = data?.migrations || [];

    // Filter migrations
    const filteredMigrations = migrations.filter((m) => {
        const matchesSearch =
            m.company_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            m.migration_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
            m.qb_file_name.toLowerCase().includes(searchQuery.toLowerCase());

        const matchesStatus = statusFilter === "all" || m.status === statusFilter;

        return matchesSearch && matchesStatus;
    });

    const handleStart = (id: string) => {
        // In production, this would open a modal for QBO credentials
        console.log("Start migration:", id);
    };

    const handleCancel = (id: string) => {
        if (confirm("Are you sure you want to cancel this migration?")) {
            cancelMutation.mutate(id);
        }
    };

    const handleRetry = (id: string) => {
        retryMutation.mutate(id);
    };

    const handleBulkAction = (action: "start" | "cancel") => {
        if (selectedIds.size === 0) return;

        if (action === "cancel") {
            if (confirm(`Cancel ${selectedIds.size} selected migrations?`)) {
                selectedIds.forEach((id) => cancelMutation.mutate(id));
            }
        }
        setSelectedIds(new Set());
    };

    const statusOptions = [
        { value: "all", label: "All Statuses" },
        { value: "pending", label: "Pending" },
        { value: "uploaded", label: "Ready" },
        { value: "processing", label: "Processing" },
        { value: "completed", label: "Completed" },
        { value: "failed", label: "Failed" },
    ];

    return (
        <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Bulk Migration Manager</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Manage and monitor all client migrations from one place
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => refetch()}
                        className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                        Refresh
                    </button>
                    <button className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                        <Download className="w-4 h-4" />
                        Export
                    </button>
                </div>
            </div>

            {/* Filters */}
            <div className="card-forensic p-4">
                <div className="flex flex-wrap items-center gap-4">
                    {/* Search */}
                    <div className="flex-1 min-w-[250px]">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search by company, file name, or session ID..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 text-sm border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)] focus:border-transparent"
                            />
                        </div>
                    </div>

                    {/* Status Filter */}
                    <div className="flex items-center gap-2">
                        <Filter className="w-4 h-4 text-gray-400" />
                        <select
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            className="px-3 py-2 text-sm border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                        >
                            {statusOptions.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Bulk Actions */}
                    {selectedIds.size > 0 && (
                        <div className="flex items-center gap-2 pl-4 border-l border-[var(--border)]">
                            <span className="text-sm text-gray-500">
                                {selectedIds.size} selected
                            </span>
                            <button
                                onClick={() => handleBulkAction("start")}
                                className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-[var(--success)] hover:bg-[var(--success)]/90 rounded-lg transition-colors"
                            >
                                <Play className="w-3 h-3" />
                                Start All
                            </button>
                            <button
                                onClick={() => handleBulkAction("cancel")}
                                className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-[var(--error)] hover:bg-[var(--error)]/90 rounded-lg transition-colors"
                            >
                                <XCircle className="w-3 h-3" />
                                Cancel All
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Stats Bar */}
            <div className="grid grid-cols-5 gap-4">
                {statusOptions.slice(1).map((status) => {
                    const count = migrations.filter((m) => m.status === status.value).length;
                    return (
                        <button
                            key={status.value}
                            onClick={() => setStatusFilter(status.value)}
                            className={`p-3 rounded-lg border transition-colors ${statusFilter === status.value
                                    ? "border-[var(--bridge-blue)] bg-blue-50"
                                    : "border-[var(--border)] hover:bg-gray-50"
                                }`}
                        >
                            <p className="text-2xl font-bold tabular-nums">{count}</p>
                            <p className="text-xs text-gray-500">{status.label}</p>
                        </button>
                    );
                })}
            </div>

            {/* Migrations Table */}
            <MigrationsTable
                migrations={filteredMigrations}
                isLoading={isLoading}
                onStart={handleStart}
                onCancel={handleCancel}
                onRetry={handleRetry}
                selectedIds={selectedIds}
                onSelectionChange={setSelectedIds}
            />

            {/* Results Info */}
            <div className="text-sm text-gray-500 text-center">
                Showing {filteredMigrations.length} of {migrations.length} migrations
            </div>
        </div>
    );
}
