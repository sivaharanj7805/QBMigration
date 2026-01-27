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

    useEffect(() => {
        fetchReports();
    }, []);

    const fetchReports = async () => {
        setLoading(true);
        try {
            const response = await fetch(`${API_URL}/api/reports`, { credentials: 'include' });
            if (response.ok) {
                const data = await response.json();
                setReports(data.reports || []);
            } else {
                setReports([]);
            }
        } catch (error) {
            console.error("Failed to fetch reports:", error);
            setReports([]);
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

                {loading ? (
                    <div className="p-8 text-center text-gray-500">
                        <Loader2 className="w-8 h-8 mx-auto animate-spin mb-2" />
                        Loading reports...
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
                                            <button className="btn-secondary flex items-center gap-1 text-sm py-1.5">
                                                <Download className="w-4 h-4" />
                                                Download
                                            </button>
                                        ) : (
                                            <button className="text-gray-400 cursor-not-allowed flex items-center gap-1 text-sm">
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
                                                const response = await fetch(`${API_URL}/api/reports/generate`, {
                                                    method: 'POST',
                                                    credentials: 'include',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ type: type.type }),
                                                });
                                                if (response.ok) {
                                                    fetchReports();
                                                } else {
                                                    alert("Failed to generate report");
                                                }
                                            } catch (error) {
                                                console.error("Generate report error:", error);
                                                alert("Failed to connect to server");
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
                        <button className="text-blue-600 text-sm font-medium mt-2 flex items-center gap-1">
                            Learn more <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
