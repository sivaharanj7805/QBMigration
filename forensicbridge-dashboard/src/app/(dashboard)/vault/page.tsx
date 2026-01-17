"use client";

import { useState } from "react";
import {
    Database,
    Search,
    Calendar,
    FileText,
    Download,
    ChevronRight,
    Clock,
    Filter,
    RefreshCw,
    Lock,
    Shield
} from "lucide-react";

// Mock archived companies
const archivedCompanies = [
    {
        id: "ARC-001",
        companyName: "ABC Corporation",
        archiveDate: "Dec 15, 2025",
        recordCount: 45892,
        storageClass: "GLACIER",
        status: "archived",
        retentionYears: 7,
        lastAccessed: "Jan 10, 2026"
    },
    {
        id: "ARC-002",
        companyName: "Smith & Associates",
        archiveDate: "Nov 20, 2025",
        recordCount: 23456,
        storageClass: "GLACIER",
        status: "archived",
        retentionYears: 7,
        lastAccessed: "Dec 5, 2025"
    },
    {
        id: "ARC-003",
        companyName: "Northern Manufacturing",
        archiveDate: "Oct 8, 2025",
        recordCount: 78234,
        storageClass: "GLACIER",
        status: "restoring",
        retentionYears: 7,
        lastAccessed: "Restoring..."
    },
    {
        id: "ARC-004",
        companyName: "Coastal Exports Ltd",
        archiveDate: "Sep 1, 2025",
        recordCount: 12567,
        storageClass: "STANDARD",
        status: "available",
        retentionYears: 7,
        lastAccessed: "Available Now"
    }
];

export default function VaultPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedArchive, setSelectedArchive] = useState<string | null>(null);

    const filteredArchives = archivedCompanies.filter(a =>
        a.companyName.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "available":
                return <span className="badge badge-success">Available</span>;
            case "restoring":
                return (
                    <span className="badge badge-warning flex items-center gap-1">
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Restoring
                    </span>
                );
            default:
                return <span className="badge badge-gray">In Glacier</span>;
        }
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Data Museum</h1>
                    <p className="text-gray-500 mt-1">Browse and restore archived QuickBooks data</p>
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-500">
                    <Lock className="w-4 h-4" />
                    <span>7-Year Legal Retention</span>
                </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">4</p>
                            <p className="stat-card-label">Archived Companies</p>
                        </div>
                        <div className="stat-card-icon bg-blue-50 text-blue-600">
                            <Database className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">160K</p>
                            <p className="stat-card-label">Total Records</p>
                        </div>
                        <div className="stat-card-icon bg-green-50 text-green-600">
                            <FileText className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">2.4 GB</p>
                            <p className="stat-card-label">Glacier Storage</p>
                        </div>
                        <div className="stat-card-icon bg-purple-50 text-purple-600">
                            <Shield className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">$0.12</p>
                            <p className="stat-card-label">Monthly Cost</p>
                        </div>
                        <div className="stat-card-icon bg-yellow-50 text-yellow-600">
                            <Clock className="w-5 h-5" />
                        </div>
                    </div>
                </div>
            </div>

            {/* Search */}
            <div className="card-forensic p-4">
                <div className="flex items-center gap-4">
                    <div className="flex-1 relative">
                        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                            type="text"
                            placeholder="Search archived companies, transactions, dates..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="input pl-10"
                        />
                    </div>
                    <button className="btn-secondary flex items-center gap-2">
                        <Filter className="w-4 h-4" />
                        Filters
                    </button>
                    <button className="btn-secondary flex items-center gap-2">
                        <Calendar className="w-4 h-4" />
                        Date Range
                    </button>
                </div>
            </div>

            {/* Archives List */}
            <div className="card-forensic">
                <div className="px-6 py-4 border-b border-gray-100">
                    <h2 className="font-semibold text-gray-900">Archived Companies</h2>
                </div>

                <div className="divide-y divide-gray-100">
                    {filteredArchives.map((archive) => (
                        <div
                            key={archive.id}
                            className={`p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50 ${selectedArchive === archive.id ? "bg-blue-50" : ""
                                }`}
                            onClick={() => setSelectedArchive(archive.id)}
                        >
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
                                    <Database className="w-6 h-6 text-gray-500" />
                                </div>
                                <div>
                                    <p className="font-medium text-gray-900">{archive.companyName}</p>
                                    <p className="text-sm text-gray-500">
                                        {archive.recordCount.toLocaleString()} records • Archived {archive.archiveDate}
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-6">
                                <div className="text-right">
                                    <p className="text-sm text-gray-500">{archive.retentionYears}-Year Retention</p>
                                    <p className="text-xs text-gray-400">{archive.lastAccessed}</p>
                                </div>

                                {getStatusBadge(archive.status)}

                                {archive.status === "archived" && (
                                    <button
                                        className="btn-secondary text-sm py-1.5 flex items-center gap-1"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            // Would trigger restore
                                        }}
                                    >
                                        <RefreshCw className="w-4 h-4" />
                                        Restore
                                    </button>
                                )}

                                {archive.status === "available" && (
                                    <button
                                        className="btn-primary text-sm py-1.5 flex items-center gap-1"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            // Would open browser
                                        }}
                                    >
                                        <Search className="w-4 h-4" />
                                        Browse
                                    </button>
                                )}

                                <ChevronRight className="w-5 h-5 text-gray-400" />
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Info Box */}
            <div className="card-forensic p-6 bg-green-50 border-green-200">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Shield className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-green-900">Forensic Archival Service</h3>
                        <p className="text-sm text-green-700 mt-1">
                            All archived data is stored in AWS S3 Glacier with 7-year legal retention.
                            Metadata (who/what/when) is preserved, but actual financial data is purged after 24 hours.
                            Restore requests typically complete within 3-5 hours.
                        </p>
                        <div className="flex items-center gap-4 mt-3">
                            <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">WORM Compliant</span>
                            <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">SOC 2</span>
                            <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">🍁 Canada Only</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
