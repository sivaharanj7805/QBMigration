"use client";

import { useState } from "react";
import Link from "next/link";
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
    Filter
} from "lucide-react";

// Mock migrations
const migrations = [
    {
        id: "MIG-2026-001",
        companyName: "ABC Corporation",
        fileName: "ABCCorp_2024.QBW",
        startTime: "Jan 15, 2026 10:30 AM",
        duration: "4m 32s",
        status: "completed",
        recordsProcessed: 12847,
        verified: true
    },
    {
        id: "MIG-2026-002",
        companyName: "Smith & Associates",
        fileName: "SmithAssoc.QBW",
        startTime: "Jan 14, 2026 2:15 PM",
        duration: "2m 15s",
        status: "completed",
        recordsProcessed: 5621,
        verified: true
    },
    {
        id: "MIG-2026-003",
        companyName: "Northern Manufacturing",
        fileName: "NorthMfg.QBW",
        startTime: "Jan 16, 2026 9:00 AM",
        duration: "In progress",
        status: "processing",
        recordsProcessed: 19234,
        progress: 67,
        verified: false
    },
    {
        id: "MIG-2026-004",
        companyName: "Coastal Exports Ltd",
        fileName: "CoastalExports.QBB",
        startTime: "Jan 13, 2026 11:45 AM",
        duration: "3m 08s",
        status: "failed",
        recordsProcessed: 4521,
        error: "QBO API rate limit exceeded",
        verified: false
    },
    {
        id: "MIG-2026-005",
        companyName: "Downtown Retail",
        fileName: "DowntownRetail.QBW",
        startTime: "Jan 12, 2026 3:30 PM",
        duration: "1m 45s",
        status: "completed",
        recordsProcessed: 3456,
        verified: true
    }
];

export default function MigrationsPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");

    const filteredMigrations = migrations.filter(m => {
        const matchesSearch = m.companyName.toLowerCase().includes(searchTerm.toLowerCase()) ||
            m.id.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = statusFilter === "all" || m.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    const getStatusBadge = (status: string, progress?: number) => {
        switch (status) {
            case "completed":
                return <span className="badge badge-success"><CheckCircle2 className="w-3 h-3 mr-1" />Completed</span>;
            case "processing":
                return (
                    <span className="badge badge-info flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        {progress}%
                    </span>
                );
            case "failed":
                return <span className="badge badge-error"><AlertCircle className="w-3 h-3 mr-1" />Failed</span>;
            default:
                return <span className="badge badge-gray">Unknown</span>;
        }
    };

    const completedCount = migrations.filter(m => m.status === "completed").length;
    const processingCount = migrations.filter(m => m.status === "processing").length;
    const failedCount = migrations.filter(m => m.status === "failed").length;

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
                            <th>Duration</th>
                            <th>Status</th>
                            <th>Verified</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredMigrations.map((migration) => (
                            <tr key={migration.id}>
                                <td>
                                    <code className="text-[var(--bridge-blue)] text-sm">{migration.id}</code>
                                </td>
                                <td>
                                    <div>
                                        <p className="font-medium text-gray-900">{migration.companyName}</p>
                                        <p className="text-xs text-gray-500">{migration.fileName}</p>
                                    </div>
                                </td>
                                <td className="tabular-nums">{migration.recordsProcessed.toLocaleString()}</td>
                                <td>
                                    <span className="text-gray-500 flex items-center gap-1 text-sm">
                                        <Calendar className="w-3 h-3" />
                                        {migration.startTime}
                                    </span>
                                </td>
                                <td>
                                    <span className="text-gray-600 flex items-center gap-1 tabular-nums">
                                        <Timer className="w-3 h-3" />
                                        {migration.duration}
                                    </span>
                                </td>
                                <td>{getStatusBadge(migration.status, migration.progress)}</td>
                                <td>
                                    {migration.verified ? (
                                        <span className="text-green-600">✓ Verified</span>
                                    ) : (
                                        <span className="text-gray-400">—</span>
                                    )}
                                </td>
                                <td>
                                    <Link
                                        href={`/migrations/${migration.id}`}
                                        className="btn-secondary text-sm py-1.5 flex items-center gap-1"
                                    >
                                        View <ArrowUpRight className="w-3 h-3" />
                                    </Link>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
