"use client";

import { useState, useEffect } from "react";
import {
    FileSpreadsheet,
    Download,
    Calendar,
    BarChart3,
    FileCheck,
    AlertTriangle,
    Clock,
    ChevronRight,
    RefreshCw,
    Loader2,
    FileX
} from "lucide-react";

// Types
interface Report {
    id: string;
    type: string;
    name: string;
    company: string;
    date: string;
    status: string;
    description: string;
}

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

const reportTypes = [
    {
        type: "variance",
        name: "Variance Report",
        icon: BarChart3,
        color: "bg-blue-100 text-blue-600",
        description: "Side-by-side P&L and Balance Sheet comparison (3 years)"
    },
    {
        type: "health",
        name: "Health Check PDF",
        icon: FileCheck,
        color: "bg-green-100 text-green-600",
        description: "Pre-migration readiness report (Red/Yellow/Green)"
    },
    {
        type: "discrepancy",
        name: "Discrepancy Report",
        icon: AlertTriangle,
        color: "bg-yellow-100 text-yellow-600",
        description: "Auto-generated when trial balance doesn't match"
    },
    {
        type: "certificate",
        name: "Audit Certificate",
        icon: FileSpreadsheet,
        color: "bg-purple-100 text-purple-600",
        description: "Professional PDF with SHA-256 verification"
    }
];

export default function ReportsPage() {
    const [filter, setFilter] = useState<string>("all");
    const [loading, setLoading] = useState(true);
    const [reports, setReports] = useState<Report[]>([]);
    const [showGenerateModal, setShowGenerateModal] = useState(false);
    const [downloadingId, setDownloadingId] = useState<string | null>(null);
    // FIX: Add error state to distinguish from empty state
    const [error, setError] = useState<string | null>(null);

    // FIX: Add download error state for UI feedback
    const [downloadError, setDownloadError] = useState<string | null>(null);

    const handleDownloadReport = async (reportId: string, reportName: string) => {
        setDownloadingId(reportId);
        setDownloadError(null);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${API_URL}/api/reports/${reportId}/download`, {
                credentials: 'include',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${reportName.replace(/\s+/g, '_')}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                // FIX: Better error message based on status
                let errorMsg = "Failed to download report.";
                if (response.status === 401) {
                    errorMsg = "Session expired. Please log in again.";
                } else if (response.status === 404) {
                    errorMsg = "Report not found. It may have been deleted.";
                } else if (response.status >= 500) {
                    errorMsg = `Server error (${response.status}). Please try again later.`;
                }
                setDownloadError(errorMsg);
            }
        } catch (err) {
            // FIX: Use proper error logging and state
            const errorMessage = err instanceof Error ? err.message : "Network error";
            setDownloadError(`Failed to connect: ${errorMessage}`);
            if (process.env.NODE_ENV === 'development') {
                console.error("Download error:", err);
            }
        } finally {
            setDownloadingId(null);
        }
    };

    useEffect(() => {
        fetchReports();
    }, []);

    const fetchReports = async () => {
        setLoading(true);
        setError(null);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${API_URL}/api/reports`, {
                credentials: 'include',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            });
            if (response.ok) {
                const data = await response.json();
                setReports(data.reports || []);
            } else {
                // FIX: Set error state instead of silent failure
                const errorText = response.status === 401
                    ? "Session expired. Please log in again."
                    : `Failed to load reports (${response.status})`;
                setError(errorText);
                setReports([]);
            }
        } catch (err) {
            // FIX: Track error state and use proper error logging
            const errorMessage = err instanceof Error ? err.message : "Network error";
            setError(`Failed to connect to server: ${errorMessage}`);
            setReports([]);
            if (process.env.NODE_ENV === 'development') {
                console.error("Failed to fetch reports:", err);
            }
        } finally {
            setLoading(false);
        }
    };

    const filteredReports = filter === "all"
        ? reports
        : reports.filter(r => r.type === filter);

    const getStatusBadge = (status: string) => {
        if (status === "ready") {
            return <span className="badge badge-success">Ready</span>;
        }
        return (
            <span className="badge badge-warning flex items-center gap-1">
                <Clock className="w-3 h-3 animate-spin" />
                Generating
            </span>
        );
    };

    const getTypeIcon = (type: string) => {
        const config = reportTypes.find(r => r.type === type);
        if (!config) return null;
        const Icon = config.icon;
        return (
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${config.color}`}>
                <Icon className="w-5 h-5" />
            </div>
        );
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
                    <p className="text-gray-500 mt-1">Generate and download verification reports</p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={fetchReports}
                        className="btn-secondary flex items-center gap-2"
                        disabled={loading}
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                    <button
                        className="btn-primary flex items-center gap-2"
                        onClick={() => setShowGenerateModal(true)}
                    >
                        <FileSpreadsheet className="w-4 h-4" />
                        Generate New Report
                    </button>
                </div>
            </div>

            {/* Report Type Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {reportTypes.map((type) => {
                    const Icon = type.icon;
                    return (
                        <button
                            key={type.type}
                            onClick={() => setFilter(filter === type.type ? "all" : type.type)}
                            className={`card-forensic-hover p-4 text-left ${filter === type.type ? "ring-2 ring-[var(--bridge-blue)]" : ""
                                }`}
                        >
                            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${type.color} mb-3`}>
                                <Icon className="w-5 h-5" />
                            </div>
                            <h3 className="font-semibold text-gray-900">{type.name}</h3>
                            <p className="text-xs text-gray-500 mt-1">{type.description}</p>
                        </button>
                    );
                })}
            </div>

            {/* Reports Table */}
            <div className="card-forensic">
                <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                    <h2 className="font-semibold text-gray-900">Generated Reports</h2>
                    <span className="text-sm text-gray-500">{loading ? "--" : filteredReports.length} reports</span>
                </div>

                {/* FIX: Show download error if present */}
                {downloadError && (
                    <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                        {downloadError}
                        <button
                            onClick={() => setDownloadError(null)}
                            className="ml-auto text-red-500 hover:text-red-700"
                        >
                            Dismiss
                        </button>
                    </div>
                )}

                {loading ? (
                    <div className="p-8 text-center text-gray-500">
                        <Loader2 className="w-8 h-8 mx-auto animate-spin mb-2" />
                        Loading reports...
                    </div>
                ) : error ? (
                    // FIX: Show error state distinctly from empty state
                    <div className="p-8 text-center">
                        <AlertTriangle className="w-12 h-12 mx-auto text-red-400 mb-3" />
                        <p className="text-lg font-medium text-gray-900">Failed to load reports</p>
                        <p className="text-sm text-gray-500 mt-1">{error}</p>
                        <button
                            onClick={fetchReports}
                            className="mt-4 btn-secondary"
                        >
                            Try Again
                        </button>
                    </div>
                ) : filteredReports.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        <FileX className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                        <p className="text-lg font-medium text-gray-600">No reports generated yet</p>
                        <p className="text-sm">Complete a migration to generate verification reports</p>
                    </div>
                ) : (
                    <table className="table-forensic">
                        <thead>
                            <tr>
                                <th>Report</th>
                                <th>Company</th>
                                <th>Date</th>
                                <th>Status</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredReports.map((report) => (
                                <tr key={report.id}>
                                    <td>
                                        <div className="flex items-center gap-3">
                                            {getTypeIcon(report.type)}
                                            <div>
                                                <p className="font-medium text-gray-900">{report.name}</p>
                                                <p className="text-xs text-gray-500">{report.description}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="text-gray-600">{report.company}</td>
                                    <td>
                                        <span className="text-gray-500 flex items-center gap-1">
                                            <Calendar className="w-3 h-3" />
                                            {report.date}
                                        </span>
                                    </td>
                                    <td>{getStatusBadge(report.status)}</td>
                                    <td>
                                        {report.status === "ready" ? (
                                            <button
                                                className="btn-secondary flex items-center gap-1 text-sm py-1.5"
                                                onClick={() => handleDownloadReport(report.id, report.name)}
                                                disabled={downloadingId === report.id}
                                            >
                                                {downloadingId === report.id ? (
                                                    <Loader2 className="w-4 h-4 animate-spin" />
                                                ) : (
                                                    <Download className="w-4 h-4" />
                                                )}
                                                {downloadingId === report.id ? "Downloading..." : "Download"}
                                            </button>
                                        ) : (
                                            <button className="text-gray-400 cursor-not-allowed flex items-center gap-1 text-sm" disabled>
                                                <Clock className="w-4 h-4" />
                                                Processing
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Generate Report Modal */}
            {showGenerateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
                        <h3 className="text-lg font-semibold text-gray-900 mb-4">Generate New Report</h3>
                        <p className="text-sm text-gray-600 mb-4">
                            Select a report type to generate from your completed migrations.
                        </p>
                        <div className="space-y-2">
                            {reportTypes.map((type) => {
                                const Icon = type.icon;
                                return (
                                    <button
                                        key={type.type}
                                        className="w-full p-3 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 text-left flex items-center gap-3 transition-colors"
                                        onClick={async () => {
                                            setShowGenerateModal(false);
                                            try {
                                                const token = localStorage.getItem('token');
                                                const response = await fetch(`${API_URL}/api/reports/generate`, {
                                                    method: 'POST',
                                                    credentials: 'include',
                                                    headers: {
                                                        'Content-Type': 'application/json',
                                                        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
                                                    },
                                                    body: JSON.stringify({ type: type.type }),
                                                });
                                                if (response.ok) {
                                                    fetchReports();
                                                } else {
                                                    // FIX: Better error handling
                                                    let errorMsg = "Failed to generate report";
                                                    try {
                                                        const errorData = await response.json();
                                                        errorMsg = errorData.error || errorMsg;
                                                    } catch {
                                                        // Response wasn't JSON
                                                    }
                                                    setDownloadError(errorMsg);
                                                }
                                            } catch (err) {
                                                // FIX: Use proper error logging
                                                const errorMessage = err instanceof Error ? err.message : "Network error";
                                                setDownloadError(`Failed to connect: ${errorMessage}`);
                                                if (process.env.NODE_ENV === 'development') {
                                                    console.error("Generate report error:", err);
                                                }
                                            }
                                        }}
                                    >
                                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${type.color}`}>
                                            <Icon className="w-4 h-4" />
                                        </div>
                                        <div>
                                            <p className="font-medium text-sm text-gray-900">{type.name}</p>
                                            <p className="text-xs text-gray-500">{type.description}</p>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                        <button
                            className="mt-4 w-full py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-lg"
                            onClick={() => setShowGenerateModal(false)}
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Info Card */}
            <div className="card-forensic p-6 bg-blue-50 border-blue-200">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <FileSpreadsheet className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-blue-900">Caseware Integration</h3>
                        <p className="text-sm text-blue-700 mt-1">
                            All reports include Audit_TB.csv, Audit_GL.csv with SHA-256 hashes and 58 Lead Sheet codes.
                            Direct import into Caseware Working Papers supported.
                        </p>
                        <a
                            href="https://www.caseware.com/resources/working-papers"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 text-sm font-medium mt-2 flex items-center gap-1 hover:underline"
                        >
                            Learn more <ChevronRight className="w-4 h-4" />
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}
