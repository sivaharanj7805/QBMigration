"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
    FolderKanban,
    FileSpreadsheet,
    Clock,
    CheckCircle2,
    AlertCircle,
    Search,
    Plus,
    MoreVertical,
    Calendar,
    HardDrive,
    RefreshCw,
    Loader2,
    FolderOpen
} from "lucide-react";

// Types
interface CompanyFile {
    id: string;
    companyName: string;
    fileName: string;
    fileSize: string;
    lastModified: string;
    status: string;
    entityCount: number;
    migrations: number;
}

interface ProjectStats {
    totalFiles: number;
    migrated: number;
    pending: number;
    totalRecords: number;
}

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export default function ProjectsPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [loading, setLoading] = useState(true);
    const [companyFiles, setCompanyFiles] = useState<CompanyFile[]>([]);
    const [stats, setStats] = useState<ProjectStats>({
        totalFiles: 0,
        migrated: 0,
        pending: 0,
        totalRecords: 0
    });

    useEffect(() => {
        fetchProjectData();
    }, []);

    const fetchProjectData = async () => {
        setLoading(true);
        try {
            // TODO: Fetch from real API endpoint when available
            // const response = await fetch(`${API_URL}/api/projects`, { credentials: 'include' });
            // if (response.ok) {
            //     const data = await response.json();
            //     setCompanyFiles(data.files || []);
            //     setStats(data.stats || { totalFiles: 0, migrated: 0, pending: 0, totalRecords: 0 });
            // }

            // For now, start with empty data
            setCompanyFiles([]);
            setStats({
                totalFiles: 0,
                migrated: 0,
                pending: 0,
                totalRecords: 0
            });
        } catch (error) {
            console.error("Failed to fetch project data:", error);
        } finally {
            setLoading(false);
        }
    };

    const filteredFiles = companyFiles.filter(f =>
        f.companyName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        f.fileName.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const formatRecords = (count: number): string => {
        if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
        if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
        return count.toString();
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "migrated":
                return <span className="badge badge-success"><CheckCircle2 className="w-3 h-3 mr-1" />Migrated</span>;
            case "pending":
                return <span className="badge badge-warning"><Clock className="w-3 h-3 mr-1" />Pending</span>;
            case "error":
                return <span className="badge badge-error"><AlertCircle className="w-3 h-3 mr-1" />Error</span>;
            default:
                return <span className="badge badge-gray">Unknown</span>;
        }
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Company Files</h1>
                    <p className="text-gray-500 mt-1">Manage your QuickBooks company files</p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={fetchProjectData}
                        className="btn-secondary flex items-center gap-2"
                        disabled={loading}
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                    <Link href="/projects/new" className="btn-primary flex items-center gap-2">
                        <Plus className="w-4 h-4" />
                        Add Company File
                    </Link>
                </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{loading ? "--" : stats.totalFiles}</p>
                            <p className="stat-card-label">Total Files</p>
                        </div>
                        <div className="stat-card-icon bg-blue-50 text-blue-600">
                            <FolderKanban className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{loading ? "--" : stats.migrated}</p>
                            <p className="stat-card-label">Migrated</p>
                        </div>
                        <div className="stat-card-icon bg-green-50 text-green-600">
                            <CheckCircle2 className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{loading ? "--" : stats.pending}</p>
                            <p className="stat-card-label">Pending</p>
                        </div>
                        <div className="stat-card-icon bg-yellow-50 text-yellow-600">
                            <Clock className="w-5 h-5" />
                        </div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{loading ? "--" : formatRecords(stats.totalRecords)}</p>
                            <p className="stat-card-label">Total Records</p>
                        </div>
                        <div className="stat-card-icon bg-purple-50 text-purple-600">
                            <FileSpreadsheet className="w-5 h-5" />
                        </div>
                    </div>
                </div>
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                    type="text"
                    placeholder="Search company files..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="input pl-10"
                />
            </div>

            {/* Files Table */}
            <div className="card-forensic">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">
                        <Loader2 className="w-8 h-8 mx-auto animate-spin mb-2" />
                        Loading company files...
                    </div>
                ) : filteredFiles.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        <FolderOpen className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                        <p className="text-lg font-medium text-gray-600">No company files yet</p>
                        <p className="text-sm">Upload a QuickBooks file to get started</p>
                    </div>
                ) : (
                    <table className="table-forensic">
                        <thead>
                            <tr>
                                <th>Company</th>
                                <th>File</th>
                                <th>Size</th>
                                <th>Records</th>
                                <th>Last Modified</th>
                                <th>Status</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredFiles.map((file) => (
                                <tr key={file.id}>
                                    <td>
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
                                                <FolderKanban className="w-5 h-5 text-[var(--bridge-blue)]" />
                                            </div>
                                            <span className="font-medium text-gray-900">{file.companyName}</span>
                                        </div>
                                    </td>
                                    <td>
                                        <span className="text-gray-600 flex items-center gap-2">
                                            <HardDrive className="w-4 h-4" />
                                            {file.fileName}
                                        </span>
                                    </td>
                                    <td className="text-gray-500">{file.fileSize}</td>
                                    <td className="tabular-nums">{file.entityCount.toLocaleString()}</td>
                                    <td>
                                        <span className="text-gray-500 flex items-center gap-1">
                                            <Calendar className="w-3 h-3" />
                                            {file.lastModified}
                                        </span>
                                    </td>
                                    <td>{getStatusBadge(file.status)}</td>
                                    <td>
                                        <div className="flex items-center gap-2">
                                            <Link
                                                href={`/migrations/${file.id}`}
                                                className="text-[var(--bridge-blue)] hover:underline text-sm"
                                            >
                                                View
                                            </Link>
                                            <button className="p-1.5 hover:bg-gray-100 rounded">
                                                <MoreVertical className="w-4 h-4 text-gray-400" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
