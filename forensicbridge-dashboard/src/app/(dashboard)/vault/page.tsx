"use client";

import { useState, useEffect } from "react";
import {
    Database,
    Search,
    Calendar,
    FileText,
    ChevronRight,
    Clock,
    Filter,
    RefreshCw,
    Lock,
    Shield,
    Archive,
    Loader2
} from "lucide-react";

// Types
interface ArchivedCompany {
    id: string;
    companyName: string;
    archiveDate: string;
    recordCount: number;
    storageClass: string;
    status: string;
    retentionYears: number;
    lastAccessed: string;
}

interface VaultStats {
    archivedCompanies: number;
    totalRecords: number;
    storageSize: string;
    monthlyCost: string;
}

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export default function VaultPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedArchive, setSelectedArchive] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    // FIX: Add error state for restore operations instead of using alert()
    const [restoreError, setRestoreError] = useState<string | null>(null);
    const [restoringId, setRestoringId] = useState<string | null>(null);

    // Real data from API - starts at 0/empty
    const [archivedCompanies, setArchivedCompanies] = useState<ArchivedCompany[]>([]);
    const [stats, setStats] = useState<VaultStats>({
        archivedCompanies: 0,
        totalRecords: 0,
        storageSize: "0 GB",
        monthlyCost: "$0.00"
    });

    useEffect(() => {
        fetchVaultData();
    }, []);

    const fetchVaultData = async () => {
        setLoading(true);
        try {
            const response = await fetch(`${API_URL}/api/vault`, { credentials: 'include' });
            if (response.ok) {
                const data = await response.json();
                setArchivedCompanies(data.companies || []);
                setStats(data.stats || { archivedCompanies: 0, totalRecords: 0, storageSize: "0 GB", monthlyCost: "$0.00" });
            } else {
                setArchivedCompanies([]);
                setStats({ archivedCompanies: 0, totalRecords: 0, storageSize: "0 GB", monthlyCost: "$0.00" });
            }
        } catch (error) {
            // FIX: Only log errors in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error("Failed to fetch vault data:", error);
            }
            setArchivedCompanies([]);
            setStats({ archivedCompanies: 0, totalRecords: 0, storageSize: "0 GB", monthlyCost: "$0.00" });
        } finally {
            setLoading(false);
        }
    };

    // FIX: Add search term sanitization and length limits
    const MAX_SEARCH_LENGTH = 100;
    const sanitizedSearchTerm = searchTerm
        .slice(0, MAX_SEARCH_LENGTH) // Limit length
        .trim()
        .toLowerCase();

    const filteredArchives = archivedCompanies.filter(a => {
        // Guard against missing companyName
        const companyName = a.companyName || '';
        return companyName.toLowerCase().includes(sanitizedSearchTerm);
    });

    const formatRecords = (count: number): string => {
        if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
        if (count >= 1000) return `${(count / 1000).toFixed(0)}K`;
        return count.toString();
    };

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
            {/* FIX: Error toast for restore errors */}
            {restoreError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-red-700">
                        <Database className="w-5 h-5" />
                        {restoreError}
                    </div>
                    <button
                        onClick={() => setRestoreError(null)}
                        className="text-red-500 hover:text-red-700 text-sm"
                    >
                        Dismiss
                    </button>
                </div>
            )}

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Data Museum</h1>
                    <p className="text-gray-500 mt-1">Browse and restore archived QuickBooks data</p>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Lock className="w-4 h-4" />
                        <span>7-Year Legal Retention</span>
                    </div>
                    <button
                        onClick={fetchVaultData}
                        className="btn-secondary flex items-center gap-2"
                        disabled={loading}
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{loading ? "--" : stats.archivedCompanies}</p>
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
                            <p className="stat-card-value">{loading ? "--" : formatRecords(stats.totalRecords)}</p>
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
                            <p className="stat-card-value">{loading ? "--" : stats.storageSize}</p>
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
                            <p className="stat-card-value">{loading ? "--" : stats.monthlyCost}</p>
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

                {loading ? (
                    <div className="p-8 text-center text-gray-500">
                        <Loader2 className="w-8 h-8 mx-auto animate-spin mb-2" />
                        Loading archives...
                    </div>
                ) : filteredArchives.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        <Archive className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                        <p className="text-lg font-medium text-gray-600">No archived companies yet</p>
                        <p className="text-sm">Completed migrations will appear here after 7 days</p>
                    </div>
                ) : (
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
                                            disabled={restoringId === archive.id}
                                            onClick={async (e) => {
                                                e.stopPropagation();
                                                setRestoreError(null);
                                                setRestoringId(archive.id);
                                                try {
                                                    const response = await fetch(`${API_URL}/api/vault/${archive.id}/restore`, {
                                                        method: 'POST',
                                                        credentials: 'include',
                                                    });
                                                    if (response.ok) {
                                                        fetchVaultData();
                                                    } else {
                                                        // FIX: Use error state instead of alert
                                                        const errorMsg = response.status === 401
                                                            ? "Session expired. Please log in again."
                                                            : "Failed to initiate restore. Please try again.";
                                                        setRestoreError(errorMsg);
                                                    }
                                                } catch (error) {
                                                    // FIX: Only log in development
                                                    if (process.env.NODE_ENV === 'development') {
                                                        console.error("Restore error:", error);
                                                    }
                                                    setRestoreError("Failed to connect to server. Please check your connection.");
                                                } finally {
                                                    setRestoringId(null);
                                                }
                                            }}
                                        >
                                            {restoringId === archive.id ? (
                                                <RefreshCw className="w-4 h-4 animate-spin" />
                                            ) : (
                                                <RefreshCw className="w-4 h-4" />
                                            )}
                                            {restoringId === archive.id ? "Restoring..." : "Restore"}
                                        </button>
                                    )}

                                    {archive.status === "available" && (
                                        <button
                                            className="btn-primary text-sm py-1.5 flex items-center gap-1"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                window.open(`/vault/${archive.id}`, '_blank');
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
                )}
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

