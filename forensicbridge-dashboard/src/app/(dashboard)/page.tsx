"use client";

import { useState, useCallback } from "react";
import {
    Upload,
    FileSpreadsheet,
    Clock,
    CheckCircle2,
    AlertCircle,
    ArrowRight,
    Shield,
    Database,
    Download,
    ChevronRight,
    HardDrive
} from "lucide-react";

// Mock data for recent migrations
const recentMigrations = [
    {
        id: "MIG-2026-001",
        companyName: "ABC Corporation",
        fileName: "ABCCorp_2024.QBW",
        status: "completed",
        records: 12847,
        date: "Jan 15, 2026",
        duration: "4m 32s"
    },
    {
        id: "MIG-2026-002",
        companyName: "Smith & Associates",
        fileName: "SmithAssoc.QBW",
        status: "completed",
        records: 5621,
        date: "Jan 14, 2026",
        duration: "2m 15s"
    },
    {
        id: "MIG-2026-003",
        companyName: "Northern Manufacturing",
        fileName: "NorthMfg.QBW",
        status: "in_progress",
        records: 28456,
        date: "Jan 16, 2026",
        progress: 67
    }
];

const stats = [
    { label: "Migrations This Month", value: "24", icon: FileSpreadsheet, color: "bg-blue-50 text-blue-600" },
    { label: "Records Migrated", value: "1.2M", icon: Database, color: "bg-green-50 text-green-600" },
    { label: "Avg. Duration", value: "3m 42s", icon: Clock, color: "bg-purple-50 text-purple-600" },
    { label: "Success Rate", value: "99.8%", icon: Shield, color: "bg-emerald-50 text-emerald-600" }
];

export default function DashboardHome() {
    const [isDragActive, setIsDragActive] = useState(false);
    const [uploadedFile, setUploadedFile] = useState<File | null>(null);
    const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "processing" | "complete">("idle");

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setIsDragActive(true);
        } else if (e.type === "dragleave") {
            setIsDragActive(false);
        }
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragActive(false);

        const files = e.dataTransfer.files;
        if (files?.[0]) {
            const file = files[0];
            const ext = file.name.split('.').pop()?.toLowerCase();
            if (['qbw', 'qbb', 'qbm'].includes(ext || '')) {
                setUploadedFile(file);
                simulateUpload();
            }
        }
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setUploadedFile(file);
            simulateUpload();
        }
    };

    const simulateUpload = () => {
        setUploadStatus("uploading");
        setTimeout(() => setUploadStatus("processing"), 1500);
        setTimeout(() => setUploadStatus("complete"), 4000);
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "completed":
                return <span className="badge badge-success"><CheckCircle2 className="w-3 h-3 mr-1" />Completed</span>;
            case "in_progress":
                return <span className="badge badge-info"><Clock className="w-3 h-3 mr-1 animate-spin" />In Progress</span>;
            case "failed":
                return <span className="badge badge-error"><AlertCircle className="w-3 h-3 mr-1" />Failed</span>;
            default:
                return <span className="badge badge-gray">Unknown</span>;
        }
    };

    return (
        <div className="space-y-8">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Migration Dashboard</h1>
                <p className="text-gray-500 mt-1">Securely migrate QuickBooks Desktop to Online</p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat) => (
                    <div key={stat.label} className="stat-card">
                        <div className="flex items-start justify-between">
                            <div>
                                <p className="stat-card-value">{stat.value}</p>
                                <p className="stat-card-label">{stat.label}</p>
                            </div>
                            <div className={`stat-card-icon ${stat.color}`}>
                                <stat.icon className="w-5 h-5" />
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Drag & Drop Zone */}
            <div className="card-forensic p-8">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900">Start New Migration</h2>
                        <p className="text-sm text-gray-500">Drop a QuickBooks file to begin</p>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-400">
                        <HardDrive className="w-4 h-4" />
                        <span>Supports .QBW, .QBB, .QBM</span>
                    </div>
                </div>

                <div
                    className={`drop-zone ${isDragActive ? "active" : ""} ${uploadStatus !== "idle" ? "pointer-events-none" : ""}`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                >
                    {uploadStatus === "idle" && !uploadedFile && (
                        <>
                            <div className="w-16 h-16 mx-auto bg-blue-50 rounded-full flex items-center justify-center mb-4">
                                <Upload className="w-8 h-8 text-[var(--bridge-blue)]" />
                            </div>
                            <p className="text-lg font-medium text-gray-700 mb-1">
                                Drag & Drop your QuickBooks file here
                            </p>
                            <p className="text-sm text-gray-400 mb-4">or click to browse</p>
                            <label className="btn-primary cursor-pointer">
                                Select File
                                <input
                                    type="file"
                                    accept=".qbw,.qbb,.qbm"
                                    className="hidden"
                                    onChange={handleFileSelect}
                                />
                            </label>
                        </>
                    )}

                    {uploadStatus === "uploading" && (
                        <div className="text-center">
                            <div className="w-16 h-16 mx-auto bg-blue-50 rounded-full flex items-center justify-center mb-4 animate-pulse-subtle">
                                <Upload className="w-8 h-8 text-[var(--bridge-blue)]" />
                            </div>
                            <p className="text-lg font-medium text-gray-700 mb-2">Uploading {uploadedFile?.name}...</p>
                            <div className="w-64 mx-auto progress-bar">
                                <div className="progress-bar-fill" style={{ width: "60%" }} />
                            </div>
                        </div>
                    )}

                    {uploadStatus === "processing" && (
                        <div className="text-center">
                            <div className="w-16 h-16 mx-auto bg-green-50 rounded-full flex items-center justify-center mb-4">
                                <Database className="w-8 h-8 text-[var(--success)] animate-pulse" />
                            </div>
                            <p className="text-lg font-medium text-gray-700 mb-2">Extracting Data...</p>
                            <p className="text-sm text-gray-500">Computing SHA-256 integrity hashes</p>
                        </div>
                    )}

                    {uploadStatus === "complete" && (
                        <div className="text-center">
                            <div className="w-16 h-16 mx-auto bg-green-100 rounded-full flex items-center justify-center mb-4">
                                <CheckCircle2 className="w-8 h-8 text-[var(--success)]" />
                            </div>
                            <p className="text-lg font-medium text-gray-700 mb-2">Ready to Migrate!</p>
                            <p className="text-sm text-gray-500 mb-4">{uploadedFile?.name} • 12,847 records detected</p>
                            <div className="flex items-center justify-center gap-3">
                                <button className="btn-primary flex items-center gap-2">
                                    Migrate to QBO <ArrowRight className="w-4 h-4" />
                                </button>
                                <button className="btn-secondary flex items-center gap-2">
                                    <Download className="w-4 h-4" /> Caseware Bundle
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Recent Migrations */}
            <div className="card-forensic">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <h2 className="text-lg font-semibold text-gray-900">Recent Migrations</h2>
                    <button className="text-sm text-[var(--bridge-blue)] hover:underline flex items-center gap-1">
                        View All <ChevronRight className="w-4 h-4" />
                    </button>
                </div>

                <table className="table-forensic">
                    <thead>
                        <tr>
                            <th>Company</th>
                            <th>File</th>
                            <th>Records</th>
                            <th>Duration</th>
                            <th>Date</th>
                            <th>Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {recentMigrations.map((migration) => (
                            <tr key={migration.id}>
                                <td>
                                    <span className="font-medium text-gray-900">{migration.companyName}</span>
                                </td>
                                <td>
                                    <span className="text-gray-500 flex items-center gap-2">
                                        <FileSpreadsheet className="w-4 h-4" />
                                        {migration.fileName}
                                    </span>
                                </td>
                                <td>
                                    <span className="tabular-nums">{migration.records.toLocaleString()}</span>
                                </td>
                                <td>
                                    <span className="tabular-nums text-gray-500">
                                        {migration.duration || `${migration.progress}%`}
                                    </span>
                                </td>
                                <td>
                                    <span className="text-gray-500">{migration.date}</span>
                                </td>
                                <td>{getStatusBadge(migration.status)}</td>
                                <td>
                                    <button className="text-[var(--bridge-blue)] hover:underline text-sm">
                                        View
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <button className="card-forensic-hover p-6 text-left group">
                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center mb-3 group-hover:bg-blue-100 transition-colors">
                        <FileSpreadsheet className="w-5 h-5 text-[var(--bridge-blue)]" />
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-1">Generate Reports</h3>
                    <p className="text-sm text-gray-500">Create variance reports and audit certificates</p>
                </button>

                <button className="card-forensic-hover p-6 text-left group">
                    <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center mb-3 group-hover:bg-green-100 transition-colors">
                        <Database className="w-5 h-5 text-[var(--success)]" />
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-1">Data Museum</h3>
                    <p className="text-sm text-gray-500">Browse archived historical data</p>
                </button>

                <button className="card-forensic-hover p-6 text-left group">
                    <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center mb-3 group-hover:bg-purple-100 transition-colors">
                        <Shield className="w-5 h-5 text-purple-600" />
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-1">Verification Center</h3>
                    <p className="text-sm text-gray-500">View reconciliation status and hash chains</p>
                </button>
            </div>
        </div>
    );
}
