"use client";

import { useState, useEffect, useCallback } from "react";
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
    HardDrive,
    RefreshCw,
    Loader2
} from "lucide-react";
import { authFetch, getAuthHeader } from "@/lib/auth";
import { sanitize } from "@/lib/sanitize";
import { useRouter } from "next/navigation";
import Link from "next/link";

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

// Types
interface Migration {
    id: string;
    migration_id: string;
    companyName: string;
    company_name?: string;
    fileName: string;
    qb_file_name?: string;
    status: string;
    records: number;
    total_records?: number;
    date: string;
    created_at?: string;
    progress?: number;
    progress_percent?: number;
}

interface Stats {
    migrations_this_month: number;
    total_records: string;
    avg_duration: string;
    success_rate: string;
}

// Constants
const MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024; // 5GB
const VALID_EXTENSIONS = ['.qbw', '.qbb', '.qbm'];

/**
 * Validate QuickBooks file
 * SECURITY: Prevents double-extension attacks and validates file type
 */
function isValidQBFile(fileName: string): boolean {
    const normalizedName = fileName.trim().toLowerCase();

    // Only allow files that end with exactly one of the valid extensions
    const hasValidExtension = VALID_EXTENSIONS.some(ext => normalizedName.endsWith(ext));

    // Reject files with multiple extensions (common attack vector)
    const extensionCount = (normalizedName.match(/\.[a-z0-9]+/g) || []).length;
    if (extensionCount > 1) {
        return false;
    }

    return hasValidExtension;
}

/**
 * Format date for display
 */
function formatDate(isoDate: string | null): string {
    if (!isoDate) return "--";
    try {
        const date = new Date(isoDate);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    } catch {
        return "--";
    }
}

/**
 * Status Badge Component
 */
function StatusBadge({ status }: { status: string }) {
    switch (status) {
        case "completed":
            return (
                <span className="badge badge-success">
                    <CheckCircle2 className="w-3 h-3 mr-1" />
                    Completed
                </span>
            );
        case "processing":
        case "queued":
            return (
                <span className="badge badge-info">
                    <Clock className="w-3 h-3 mr-1 animate-spin" />
                    In Progress
                </span>
            );
        case "failed":
            return (
                <span className="badge badge-error">
                    <AlertCircle className="w-3 h-3 mr-1" />
                    Failed
                </span>
            );
        case "uploaded":
            return <span className="badge badge-warning">Ready</span>;
        default:
            return <span className="badge badge-gray">{status}</span>;
    }
}

/**
 * Stats Card Component
 */
function StatsCard({
    value,
    label,
    icon: Icon,
    color,
    loading,
}: {
    value: string;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    loading: boolean;
}) {
    return (
        <div className="stat-card">
            <div className="flex items-start justify-between">
                <div>
                    <p className="stat-card-value">{loading ? "--" : value}</p>
                    <p className="stat-card-label">{label}</p>
                </div>
                <div className={`stat-card-icon ${color}`}>
                    <Icon className="w-5 h-5" />
                </div>
            </div>
        </div>
    );
}

export default function DashboardHome() {
    const router = useRouter();
    const [isDragActive, setIsDragActive] = useState(false);
    const [uploadedFile, setUploadedFile] = useState<File | null>(null);
    const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "processing" | "complete" | "error">("idle");
    const [uploadError, setUploadError] = useState<string | null>(null);

    // Real data from API
    const [migrations, setMigrations] = useState<Migration[]>([]);
    const [stats, setStats] = useState<Stats>({
        migrations_this_month: 0,
        total_records: "0",
        avg_duration: "--",
        success_rate: "100%"
    });
    const [loading, setLoading] = useState(true);
    const [apiConnected, setApiConnected] = useState<boolean | null>(null);

    // Check API connection on mount
    useEffect(() => {
        checkApiConnection();
        fetchDashboardData();
    }, []);

    const checkApiConnection = async () => {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        try {
            const response = await fetch(`${API_URL}/health`, {
                method: 'GET',
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            setApiConnected(response.ok);
        } catch {
            clearTimeout(timeoutId);
            setApiConnected(false);
        }
    };

    const fetchDashboardData = async () => {
        setLoading(true);
        try {
            // Fetch stats
            const statsResponse = await authFetch(`${API_URL}/api/migrations/stats`);
            if (statsResponse.ok) {
                const statsData = await statsResponse.json();
                if (statsData.success) {
                    setStats(statsData.stats);
                }
            }

            // Fetch recent migrations
            const migrationsResponse = await authFetch(`${API_URL}/api/migrations?per_page=5`);
            if (migrationsResponse.ok) {
                const migrationsData = await migrationsResponse.json();
                if (migrationsData.success) {
                    interface ApiMigration {
                        id?: string;
                        migration_id: string;
                        company_name?: string;
                        qb_file_name?: string;
                        status: string;
                        total_records?: number;
                        created_at?: string;
                        progress_percent?: number;
                    }

                    const formattedMigrations = migrationsData.migrations.map((m: ApiMigration) => ({
                        id: m.migration_id || m.id || '',
                        migration_id: m.migration_id,
                        companyName: sanitize.text(m.company_name || "Unknown Company"),
                        fileName: sanitize.text(m.qb_file_name || "Unknown File"),
                        status: m.status,
                        records: m.total_records || 0,
                        date: formatDate(m.created_at || null),
                        progress: m.progress_percent || 0
                    }));
                    setMigrations(formattedMigrations);
                }
            }
        } catch {
            if (process.env.NODE_ENV === 'development') {
                console.error("Failed to fetch dashboard data");
            }
        } finally {
            setLoading(false);
        }
    };

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
            if (!isValidQBFile(file.name)) {
                setUploadError("Invalid file type. Please upload a .QBW, .QBB, or .QBM file. Files with multiple extensions are not allowed.");
                return;
            }
            if (file.size > MAX_FILE_SIZE) {
                setUploadError("File too large. Maximum file size is 5GB.");
                return;
            }
            if (file.size === 0) {
                setUploadError("File appears to be empty. Please select a valid QuickBooks file.");
                return;
            }
            handleFileUpload(file);
        }
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            if (!isValidQBFile(file.name)) {
                setUploadError("Invalid file type. Please upload a .QBW, .QBB, or .QBM file.");
                return;
            }
            if (file.size > MAX_FILE_SIZE) {
                setUploadError("File too large. Maximum file size is 5GB.");
                return;
            }
            if (file.size === 0) {
                setUploadError("File appears to be empty. Please select a valid QuickBooks file.");
                return;
            }
            handleFileUpload(file);
        }
    };

    const handleFileUpload = async (file: File) => {
        // FIX: Guard against double uploads - prevent concurrent upload requests
        if (uploadStatus === "uploading" || uploadStatus === "processing") {
            return;
        }

        setUploadedFile(file);
        setUploadStatus("uploading");
        setUploadError(null);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${API_URL}/api/upload`, {
                method: 'POST',
                body: formData,
                headers: getAuthHeader(true),
                credentials: 'include',
            });

            if (response.ok) {
                setUploadStatus("processing");
                setTimeout(() => {
                    setUploadStatus("complete");
                    fetchDashboardData();
                }, 2000);
            } else {
                // SECURITY FIX: Wrap response.json() in try/catch for non-OK responses
                // The response body may not be valid JSON
                let errorMessage = "Upload failed";
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorMessage;
                } catch {
                    // Response body was not valid JSON, use default error message
                    errorMessage = `Upload failed with status ${response.status}`;
                }
                setUploadError(errorMessage);
                setUploadStatus("error");
            }
        } catch {
            setUploadError("Failed to connect to server. Please try again.");
            setUploadStatus("error");
        }
    };

    const statsDisplay = [
        { label: "Migrations This Month", value: stats.migrations_this_month.toString(), icon: FileSpreadsheet, color: "bg-blue-50 text-blue-600" },
        { label: "Records Migrated", value: stats.total_records, icon: Database, color: "bg-green-50 text-green-600" },
        { label: "Avg. Duration", value: stats.avg_duration, icon: Clock, color: "bg-purple-50 text-purple-600" },
        { label: "Success Rate", value: stats.success_rate, icon: Shield, color: "bg-emerald-50 text-emerald-600" }
    ];

    return (
        <div className="space-y-8">
            {/* Header with API Status */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Migration Dashboard</h1>
                    <p className="text-gray-500 mt-1">Securely migrate QuickBooks Desktop to Online</p>
                </div>
                <div className="flex items-center gap-4">
                    {/* API Status Indicator */}
                    <div className="flex items-center gap-2 text-sm">
                        {apiConnected === null ? (
                            <span className="text-gray-400">Checking connection...</span>
                        ) : apiConnected ? (
                            <span className="flex items-center gap-1 text-green-600">
                                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                                API Connected
                            </span>
                        ) : (
                            <span className="flex items-center gap-1 text-red-600">
                                <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                                API Offline
                            </span>
                        )}
                    </div>
                    <button
                        onClick={fetchDashboardData}
                        className="btn-secondary flex items-center gap-2"
                        disabled={loading}
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {statsDisplay.map((stat) => (
                    <StatsCard
                        key={stat.label}
                        value={stat.value}
                        label={stat.label}
                        icon={stat.icon}
                        color={stat.color}
                        loading={loading}
                    />
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
                    className={`drop-zone ${isDragActive ? "active" : ""} ${uploadStatus !== "idle" && uploadStatus !== "error" ? "pointer-events-none" : ""}`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                >
                    {(uploadStatus === "idle" || uploadStatus === "error") && !uploadedFile && (
                        <>
                            <div className="w-16 h-16 mx-auto bg-blue-50 rounded-full flex items-center justify-center mb-4">
                                <Upload className="w-8 h-8 text-[var(--bridge-blue)]" />
                            </div>
                            <p className="text-lg font-medium text-gray-700 mb-1">
                                Drag & Drop your QuickBooks file here
                            </p>
                            <p className="text-sm text-gray-400 mb-4">or click to browse</p>
                            {uploadError && (
                                <p className="text-sm text-red-500 mb-4">{uploadError}</p>
                            )}
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
                                <Loader2 className="w-8 h-8 text-[var(--bridge-blue)] animate-spin" />
                            </div>
                            <p className="text-lg font-medium text-gray-700 mb-2">
                                Uploading {sanitize.text(uploadedFile?.name || '')}...
                            </p>
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
                            <p className="text-sm text-gray-500 mb-4">
                                {sanitize.text(uploadedFile?.name || '')}
                            </p>
                            <div className="flex items-center justify-center gap-3">
                                <button
                                    className="btn-primary flex items-center gap-2"
                                    onClick={() => router.push("/upload?destination=qbo")}
                                >
                                    Migrate to QBO <ArrowRight className="w-4 h-4" />
                                </button>
                                <button
                                    className="btn-secondary flex items-center gap-2"
                                    onClick={() => router.push("/upload?destination=caseware")}
                                >
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
                    <Link href="/migrations" className="text-sm text-[var(--bridge-blue)] hover:underline flex items-center gap-1">
                        View All <ChevronRight className="w-4 h-4" />
                    </Link>
                </div>

                {loading ? (
                    <div className="p-8 text-center text-gray-500">
                        <Loader2 className="w-8 h-8 mx-auto animate-spin mb-2" />
                        Loading migrations...
                    </div>
                ) : migrations.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        <FileSpreadsheet className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                        <p className="text-lg font-medium text-gray-600">No migrations yet</p>
                        <p className="text-sm">Upload a QuickBooks file above to get started</p>
                    </div>
                ) : (
                    <table className="table-forensic">
                        <thead>
                            <tr>
                                <th>Company</th>
                                <th>File</th>
                                <th>Records</th>
                                <th>Date</th>
                                <th>Status</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {migrations.map((migration) => (
                                <tr key={migration.id}>
                                    <td>
                                        <span className="font-medium text-gray-900">
                                            {migration.companyName}
                                        </span>
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
                                        <span className="text-gray-500">{migration.date}</span>
                                    </td>
                                    <td>
                                        <StatusBadge status={migration.status} />
                                    </td>
                                    <td>
                                        <Link
                                            href={`/migrations/${migration.migration_id || migration.id}`}
                                            className="text-[var(--bridge-blue)] hover:underline text-sm"
                                        >
                                            View
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <button className="card-forensic-hover p-6 text-left group" onClick={() => router.push("/reports")}>
                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center mb-3 group-hover:bg-blue-100 transition-colors">
                        <FileSpreadsheet className="w-5 h-5 text-[var(--bridge-blue)]" />
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-1">Generate Reports</h3>
                    <p className="text-sm text-gray-500">Create variance reports and audit certificates</p>
                </button>

                <button className="card-forensic-hover p-6 text-left group" onClick={() => router.push("/vault")}>
                    <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center mb-3 group-hover:bg-green-100 transition-colors">
                        <Database className="w-5 h-5 text-[var(--success)]" />
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-1">Data Museum</h3>
                    <p className="text-sm text-gray-500">Browse archived historical data</p>
                </button>

                <button className="card-forensic-hover p-6 text-left group" onClick={() => router.push("/migrations")}>
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
