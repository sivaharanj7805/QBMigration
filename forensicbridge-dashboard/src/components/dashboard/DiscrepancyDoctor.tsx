"use client";

import { useState } from "react";
import {
    AlertTriangle,
    ChevronDown,
    ChevronUp,
    Search,
    Download,
    ArrowUpRight,
    ArrowDownRight,
    DollarSign,
    Filter
} from "lucide-react";

interface AccountVariance {
    account_name: string;
    account_type: string;
    qbd_balance: number;
    qbo_balance: number;
    variance: number;
    severity: "TRIVIAL" | "MINOR" | "MODERATE" | "CRITICAL";
}

interface DiscrepancyDrilldown {
    total_variance: number;
    variance_count: number;
    matched_count: number;
    missing_count: number;
    accounts_with_variance: AccountVariance[];
    accounts_missing_in_qbo: Array<{
        account_name: string;
        account_type: string;
        balance: number;
    }>;
    recommended_actions: string[];
}

interface DiscrepancyDoctorProps {
    drilldown: DiscrepancyDrilldown | null;
    isLoading?: boolean;
    onClose?: () => void;
    migrationId?: string;
}

export function DiscrepancyDoctor({
    drilldown,
    isLoading = false,
    onClose,
    migrationId
}: DiscrepancyDoctorProps) {
    const [searchTerm, setSearchTerm] = useState("");
    const [filterSeverity, setFilterSeverity] = useState<string>("all");
    const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set());
    const [sortBy, setSortBy] = useState<"name" | "variance">("variance");

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2,
        }).format(amount);
    };

    const getSeverityBadge = (severity: string) => {
        const styles: Record<string, string> = {
            TRIVIAL: "bg-gray-100 text-gray-600",
            MINOR: "bg-blue-100 text-blue-600",
            MODERATE: "bg-yellow-100 text-yellow-700",
            CRITICAL: "bg-red-100 text-red-700"
        };
        return styles[severity] || styles.MINOR;
    };

    const toggleAccount = (accountName: string) => {
        const newSet = new Set(expandedAccounts);
        if (newSet.has(accountName)) {
            newSet.delete(accountName);
        } else {
            newSet.add(accountName);
        }
        setExpandedAccounts(newSet);
    };

    if (isLoading) {
        return (
            <div className="card-forensic p-6">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-gray-200 rounded w-1/3"></div>
                    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                    <div className="space-y-2">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="h-12 bg-gray-100 rounded"></div>
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    if (!drilldown) {
        return (
            <div className="card-forensic p-8 text-center">
                <AlertTriangle className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                <p className="text-gray-500">No discrepancy data available</p>
            </div>
        );
    }

    // Filter and sort accounts
    let filteredAccounts = drilldown.accounts_with_variance.filter(acc => {
        const matchesSearch = acc.account_name.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesSeverity = filterSeverity === "all" || acc.severity === filterSeverity;
        return matchesSearch && matchesSeverity;
    });

    if (sortBy === "variance") {
        filteredAccounts = [...filteredAccounts].sort((a, b) =>
            Math.abs(b.variance) - Math.abs(a.variance)
        );
    } else {
        filteredAccounts = [...filteredAccounts].sort((a, b) =>
            a.account_name.localeCompare(b.account_name)
        );
    }

    const handleExportCSV = () => {
        const headers = ["Account Name", "Type", "QBD Balance", "QBO Balance", "Variance", "Severity"];
        const rows = drilldown.accounts_with_variance.map(acc => [
            acc.account_name,
            acc.account_type,
            acc.qbd_balance,
            acc.qbo_balance,
            acc.variance,
            acc.severity
        ]);

        const csv = [headers, ...rows].map(row => row.join(",")).join("\n");
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `discrepancy-report-${migrationId || "export"}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="card-forensic overflow-hidden">
            {/* Header */}
            <div className="bg-red-50 border-b border-red-200 p-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                            <AlertTriangle className="w-5 h-5 text-red-600" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold text-red-900">
                                Discrepancy Doctor
                            </h2>
                            <p className="text-sm text-red-600">
                                {drilldown.variance_count} account{drilldown.variance_count !== 1 ? 's' : ''} with variance detected
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleExportCSV}
                            className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 text-gray-700 text-sm rounded-lg hover:bg-gray-50"
                        >
                            <Download className="w-4 h-4" />
                            Export CSV
                        </button>
                        {onClose && (
                            <button
                                onClick={onClose}
                                className="px-3 py-2 text-gray-500 hover:text-gray-700"
                            >
                                ✕
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gray-50 border-b">
                <div className="text-center">
                    <p className="text-2xl font-bold text-red-600">
                        {formatCurrency(drilldown.total_variance)}
                    </p>
                    <p className="text-xs text-gray-500 uppercase">Total Variance</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold text-red-600">
                        {drilldown.variance_count}
                    </p>
                    <p className="text-xs text-gray-500 uppercase">Accounts Off</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold text-green-600">
                        {drilldown.matched_count}
                    </p>
                    <p className="text-xs text-gray-500 uppercase">Matched</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold text-yellow-600">
                        {drilldown.missing_count}
                    </p>
                    <p className="text-xs text-gray-500 uppercase">Missing in QBO</p>
                </div>
            </div>

            {/* Filters */}
            <div className="p-4 flex flex-wrap gap-3 border-b">
                <div className="flex-1 min-w-[200px] relative">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search accounts..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                </div>
                <select
                    value={filterSeverity}
                    onChange={(e) => setFilterSeverity(e.target.value)}
                    className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="all">All Severities</option>
                    <option value="CRITICAL">🔴 Critical</option>
                    <option value="MODERATE">🟡 Moderate</option>
                    <option value="MINOR">🔵 Minor</option>
                    <option value="TRIVIAL">⚪ Trivial</option>
                </select>
                <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as "name" | "variance")}
                    className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="variance">Sort by Variance</option>
                    <option value="name">Sort by Name</option>
                </select>
            </div>

            {/* Account List */}
            <div className="max-h-[400px] overflow-y-auto">
                {filteredAccounts.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        <Filter className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p>No accounts match your filters</p>
                    </div>
                ) : (
                    <div className="divide-y">
                        {filteredAccounts.map((account) => (
                            <div key={account.account_name} className="hover:bg-gray-50">
                                {/* Account Row */}
                                <button
                                    className="w-full px-4 py-3 flex items-center justify-between text-left"
                                    onClick={() => toggleAccount(account.account_name)}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${account.variance > 0
                                                ? "bg-green-100 text-green-600"
                                                : "bg-red-100 text-red-600"
                                            }`}>
                                            {account.variance > 0
                                                ? <ArrowUpRight className="w-4 h-4" />
                                                : <ArrowDownRight className="w-4 h-4" />
                                            }
                                        </div>
                                        <div>
                                            <p className="font-medium text-gray-900">
                                                {account.account_name}
                                            </p>
                                            <p className="text-xs text-gray-500">
                                                {account.account_type}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <div className={`font-bold tabular-nums ${account.variance > 0 ? "text-green-600" : "text-red-600"
                                            }`}>
                                            {account.variance > 0 ? "+" : ""}{formatCurrency(account.variance)}
                                        </div>
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getSeverityBadge(account.severity)}`}>
                                            {account.severity}
                                        </span>
                                        {expandedAccounts.has(account.account_name)
                                            ? <ChevronUp className="w-4 h-4 text-gray-400" />
                                            : <ChevronDown className="w-4 h-4 text-gray-400" />
                                        }
                                    </div>
                                </button>

                                {/* Expanded Details */}
                                {expandedAccounts.has(account.account_name) && (
                                    <div className="px-4 pb-4 pt-0 ml-11 bg-gray-50 border-l-2 border-gray-200">
                                        <div className="grid grid-cols-2 gap-4 text-sm">
                                            <div>
                                                <p className="text-gray-500">QB Desktop Balance</p>
                                                <p className="font-medium tabular-nums">
                                                    {formatCurrency(account.qbd_balance)}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-gray-500">QB Online Balance</p>
                                                <p className="font-medium tabular-nums">
                                                    {formatCurrency(account.qbo_balance)}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="mt-3 p-2 bg-yellow-50 rounded text-xs text-yellow-800">
                                            💡 <strong>Suggested Fix:</strong> Check for missing transactions
                                            or opening balance adjustments in QB Online.
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Recommended Actions */}
            {drilldown.recommended_actions.length > 0 && (
                <div className="p-4 bg-yellow-50 border-t border-yellow-200">
                    <h3 className="font-medium text-yellow-900 mb-2">Recommended Actions</h3>
                    <ul className="space-y-1">
                        {drilldown.recommended_actions.map((action, i) => (
                            <li key={i} className="text-sm text-yellow-800 flex items-start gap-2">
                                <span className="font-bold">•</span>
                                {action}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
