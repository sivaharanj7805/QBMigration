"use client";

import { useState } from "react";
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
    HardDrive
} from "lucide-react";

// Mock company files
const companyFiles = [
    {
        id: "PRJ-001",
        companyName: "ABC Corporation",
        fileName: "ABCCorp_2024.QBW",
        fileSize: "245 MB",
        lastModified: "Jan 15, 2026",
        status: "migrated",
        entityCount: 12847,
        migrations: 3
    },
    {
        id: "PRJ-002",
        companyName: "Smith & Associates",
        fileName: "SmithAssoc.QBW",
        fileSize: "89 MB",
        lastModified: "Jan 14, 2026",
        status: "migrated",
        entityCount: 5621,
        migrations: 1
    },
    {
        id: "PRJ-003",
        companyName: "Northern Manufacturing",
        fileName: "NorthMfg.QBW",
        fileSize: "512 MB",
        lastModified: "Jan 16, 2026",
        status: "pending",
        entityCount: 28456,
        migrations: 0
    },
    {
        id: "PRJ-004",
        companyName: "Coastal Exports Ltd",
        fileName: "CoastalExports.QBB",
        fileSize: "156 MB",
        lastModified: "Jan 10, 2026",
        status: "error",
        entityCount: 8934,
        migrations: 1
    }
];

export default function ProjectsPage() {
    const [searchTerm, setSearchTerm] = useState("");

    const filteredFiles = companyFiles.filter(f =>
        f.companyName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        f.fileName.toLowerCase().includes(searchTerm.toLowerCase())
    );

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
                <Link href="/projects/new" className="btn-primary flex items-center gap-2">
                    <Plus className="w-4 h-4" />
                    Add Company File
                </Link>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="stat-card">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="stat-card-value">{companyFiles.length}</p>
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
                            <p className="stat-card-value">{companyFiles.filter(f => f.status === "migrated").length}</p>
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
                            <p className="stat-card-value">{companyFiles.filter(f => f.status === "pending").length}</p>
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
                            <p className="stat-card-value">55.8K</p>
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
            </div>
        </div>
    );
}
