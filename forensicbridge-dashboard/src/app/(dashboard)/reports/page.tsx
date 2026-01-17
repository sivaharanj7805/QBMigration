"use client";

import { useState } from "react";
import {
    FileSpreadsheet,
    Download,
    Calendar,
    BarChart3,
    FileCheck,
    AlertTriangle,
    Clock,
    ChevronRight
} from "lucide-react";

// Mock report data
const reports = [
    {
        id: "RPT-001",
        type: "variance",
        name: "Variance Report - ABC Corp",
        company: "ABC Corporation",
        date: "Jan 15, 2026",
        status: "ready",
        description: "3-year P&L and Balance Sheet comparison"
    },
    {
        id: "RPT-002",
        type: "health",
        name: "Health Check - Smith Associates",
        company: "Smith & Associates",
        date: "Jan 14, 2026",
        status: "ready",
        description: "Pre-migration readiness assessment"
    },
    {
        id: "RPT-003",
        type: "discrepancy",
        name: "Discrepancy Report - Northern Mfg",
        company: "Northern Manufacturing",
        date: "Jan 16, 2026",
        status: "generating",
        description: "Trial balance mismatch analysis"
    },
    {
        id: "RPT-004",
        type: "certificate",
        name: "Audit Certificate - ABC Corp",
        company: "ABC Corporation",
        date: "Jan 15, 2026",
        status: "ready",
        description: "ForensicAuditCertificate.pdf"
    }
];

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
                <button className="btn-primary flex items-center gap-2">
                    <FileSpreadsheet className="w-4 h-4" />
                    Generate New Report
                </button>
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
                    <span className="text-sm text-gray-500">{filteredReports.length} reports</span>
                </div>

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
            </div>

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
