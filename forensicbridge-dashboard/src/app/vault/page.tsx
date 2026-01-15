"use client";

import { FileText, Download, Calendar, Shield, Lock, Search, Filter } from "lucide-react";
import { useState } from "react";

// Demo data - in production this would come from the API
const demoVaultItems = [
    {
        id: "FB-2026-X99",
        company_name: "Waterloo Manufacturing",
        type: "certificate",
        created_at: "2026-01-14T15:30:00Z",
        file_size: 245000,
        hash: "0x7e2f8a9c3b...9c",
    },
    {
        id: "FB-2026-X98",
        company_name: "Smith & Associates",
        type: "certificate",
        created_at: "2026-01-13T10:20:00Z",
        file_size: 198000,
        hash: "0x4a1c5d8e2f...a1",
    },
    {
        id: "FB-2026-X97",
        company_name: "TechCorp Industries",
        type: "manifest",
        created_at: "2026-01-12T08:45:00Z",
        file_size: 512000,
        hash: "0x9b3e7f2a6c...8d",
    },
];

export default function VaultPage() {
    const [searchQuery, setSearchQuery] = useState("");
    const [typeFilter, setTypeFilter] = useState("all");

    const filteredItems = demoVaultItems.filter((item) => {
        const matchesSearch =
            item.company_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            item.id.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesType = typeFilter === "all" || item.type === typeFilter;
        return matchesSearch && matchesType;
    });

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const formatDate = (dateStr: string) => {
        return new Date(dateStr).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    };

    return (
        <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Forensic Vault</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Secure archive of all audit certificates and migration manifests
                    </p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                    <Download className="w-4 h-4" />
                    Export All
                </button>
            </div>

            {/* Security Banner */}
            <div className="card-forensic-gold p-4">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-[var(--forensic-gold)]/20 rounded-full flex items-center justify-center">
                        <Lock className="w-6 h-6 text-[var(--forensic-gold)]" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-gray-900">Tamper-Proof Storage</h3>
                        <p className="text-sm text-gray-600">
                            All documents are cryptographically signed with SHA-256 and stored
                            with immutable timestamps.
                        </p>
                    </div>
                </div>
            </div>

            {/* Filters */}
            <div className="card-forensic p-4">
                <div className="flex flex-wrap items-center gap-4">
                    <div className="flex-1 min-w-[250px]">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search by company or session ID..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 text-sm border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)] focus:border-transparent"
                            />
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Filter className="w-4 h-4 text-gray-400" />
                        <select
                            value={typeFilter}
                            onChange={(e) => setTypeFilter(e.target.value)}
                            className="px-3 py-2 text-sm border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                        >
                            <option value="all">All Types</option>
                            <option value="certificate">Certificates</option>
                            <option value="manifest">Manifests</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* Vault Items Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredItems.map((item) => (
                    <div key={item.id} className="card-forensic p-4 hover:shadow-lg transition-shadow">
                        <div className="flex items-start justify-between mb-3">
                            <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
                                {item.type === "certificate" ? (
                                    <Shield className="w-5 h-5 text-[var(--forensic-gold)]" />
                                ) : (
                                    <FileText className="w-5 h-5 text-[var(--bridge-blue)]" />
                                )}
                            </div>
                            <span
                                className={`text-xs font-medium px-2 py-1 rounded-full ${item.type === "certificate"
                                        ? "bg-yellow-50 text-yellow-700"
                                        : "bg-blue-50 text-blue-700"
                                    }`}
                            >
                                {item.type === "certificate" ? "Audit Certificate" : "Run Manifest"}
                            </span>
                        </div>

                        <h3 className="font-medium text-gray-900">{item.company_name}</h3>
                        <p className="text-xs text-gray-500 mt-1">
                            <code className="text-[var(--bridge-blue)]">{item.id}</code>
                        </p>

                        <div className="mt-4 pt-4 border-t border-gray-100 space-y-2">
                            <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-500 flex items-center gap-1">
                                    <Calendar className="w-3 h-3" /> Created
                                </span>
                                <span className="text-gray-700">{formatDate(item.created_at)}</span>
                            </div>
                            <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-500">Size</span>
                                <span className="text-gray-700">{formatFileSize(item.file_size)}</span>
                            </div>
                            <div className="flex items-center justify-between text-xs">
                                <span className="text-gray-500">SHA-256</span>
                                <code className="text-forensic-gold font-mono">{item.hash}</code>
                            </div>
                        </div>

                        <button className="w-full mt-4 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-[var(--bridge-blue)] bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors">
                            <Download className="w-4 h-4" />
                            Download
                        </button>
                    </div>
                ))}
            </div>

            {filteredItems.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                    <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>No documents found matching your criteria</p>
                </div>
            )}
        </div>
    );
}
