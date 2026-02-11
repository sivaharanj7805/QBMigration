"use client";

import { Shield, CheckCircle2, AlertCircle, Clock, ChevronDown, Copy, Check } from "lucide-react";
import { useState } from "react";

// Lead Sheet breakdown for 58 standard codes
interface LeadSheetEntry {
    code: string;
    name: string;
    category: "Assets" | "Liabilities" | "Equity" | "Income" | "COGS" | "Expenses";
    sourceBalance: number;
    destBalance: number;
    variance: number;
    isMatched: boolean;
}

interface ReconciliationShieldProps {
    // Migration page props
    sourceBalance?: number;
    destinationBalance?: number;
    discrepancy?: number;
    isBalanced?: boolean;
    forensicStatus?: "VERIFIED" | "PENDING" | "DISCREPANCY_DETECTED" | "NOT_AVAILABLE";
    verificationTimestamp?: string;
    sourceHash?: string;
    destinationHash?: string;
    hashMatch?: boolean;
    migrationId?: string;

    // Lead Sheet breakdown (58 codes) - Addresses audit gap
    leadSheetBreakdown?: LeadSheetEntry[];
    showLeadSheetDetails?: boolean;

    // Alternate props (original)
    bankAccounts?: Array<{
        name: string;
        lastReconciled: string | null;
        match: boolean;
    }>;
    overallStatus?: "verified" | "warning" | "error" | "pending";
    lastChecked?: string;
    isLoading?: boolean;
}

export function ReconciliationShield({
    sourceBalance,
    destinationBalance,
    discrepancy = 0,
    isBalanced = false,
    forensicStatus = "PENDING",
    verificationTimestamp,
    sourceHash,
    destinationHash,
    hashMatch,
    leadSheetBreakdown = [],
    showLeadSheetDetails = false,
    bankAccounts = [],
    overallStatus,
    lastChecked,
    isLoading = false
}: ReconciliationShieldProps) {
    const [expanded, setExpanded] = useState(false);
    const [copiedHash, setCopiedHash] = useState<"source" | "dest" | null>(null);
    const [showLeadSheet, setShowLeadSheet] = useState(showLeadSheetDetails);
    const [leadSheetFilter, setLeadSheetFilter] = useState<string>("all");

    // FIX: Handle NaN, Infinity, null, and undefined values for financial display
    const formatCurrency = (amount: number | null | undefined) => {
        // Guard against invalid values that could display as "NaN" or "Infinity"
        if (amount === null || amount === undefined || !Number.isFinite(amount)) {
            return "$0.00";
        }
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2,
        }).format(amount);
    };

    const copyToClipboard = (text: string, type: "source" | "dest") => {
        navigator.clipboard.writeText(text);
        setCopiedHash(type);
        setTimeout(() => setCopiedHash(null), 2000);
    };

    // Determine status from forensicStatus or overallStatus
    const getStatusConfig = () => {
        const status = (forensicStatus || overallStatus) as string;

        if (status === "VERIFIED" || status === "verified" || isBalanced) {
            return {
                bg: "bg-green-50",
                border: "border-green-200",
                iconBg: "bg-green-100",
                iconColor: "text-green-600",
                title: "Reconciliation Verified",
                subtitle: "Trial balance matches to the penny"
            };
        }
        if (status === "DISCREPANCY_DETECTED" || status === "warning") {
            return {
                bg: "bg-yellow-50",
                border: "border-yellow-200",
                iconBg: "bg-yellow-100",
                iconColor: "text-yellow-600",
                title: "Discrepancy Detected",
                subtitle: `Variance: ${formatCurrency(discrepancy)}`
            };
        }
        if (status === "error" || status === "NOT_AVAILABLE") {
            return {
                bg: "bg-red-50",
                border: "border-red-200",
                iconBg: "bg-red-100",
                iconColor: "text-red-600",
                title: "Verification Failed",
                subtitle: "Unable to verify reconciliation"
            };
        }
        return {
            bg: "bg-gray-50",
            border: "border-gray-200",
            iconBg: "bg-gray-100",
            iconColor: "text-gray-400",
            title: "Pending Verification",
            subtitle: "Waiting for migration to complete"
        };
    };

    const config = getStatusConfig();

    if (isLoading) {
        return (
            <div className="card-forensic p-6">
                <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-1/3"></div>
                    <div className="h-3 bg-gray-200 rounded w-1/2"></div>
                </div>
            </div>
        );
    }

    return (
        <div className={`card-forensic overflow-hidden border ${config.border}`}>
            {/* Header */}
            {/* AUDIT FIX LOW-7: Added aria-expanded for screen readers */}
            <button
                className={`w-full p-4 flex items-center justify-between text-left ${config.bg}`}
                onClick={() => setExpanded(!expanded)}
                aria-expanded={expanded}
                aria-label={`${config.title}: ${config.subtitle}. Click to ${expanded ? "collapse" : "expand"} details.`}
            >
                <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-full ${config.iconBg} flex items-center justify-center`}>
                        <Shield className={`w-5 h-5 ${config.iconColor}`} />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="font-semibold text-gray-900">{config.title}</h3>
                            {isBalanced ? (
                                <CheckCircle2 className={`w-4 h-4 ${config.iconColor}`} />
                            ) : discrepancy !== 0 ? (
                                <AlertCircle className={`w-4 h-4 ${config.iconColor}`} />
                            ) : (
                                <Clock className="w-4 h-4 text-gray-400" />
                            )}
                        </div>
                        <p className="text-sm text-gray-500">{config.subtitle}</p>
                    </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
            </button>

            {/* Expanded Details - Financial */}
            {expanded && sourceBalance !== undefined && (
                <div className="border-t border-gray-100 bg-white p-4 space-y-4">
                    {/* Balances */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="p-3 bg-gray-50 rounded-lg">
                            <p className="text-xs text-gray-500 uppercase mb-1">QB Desktop</p>
                            <p className="text-lg font-bold tabular-nums">{formatCurrency(sourceBalance)}</p>
                        </div>
                        <div className="p-3 bg-gray-50 rounded-lg">
                            <p className="text-xs text-gray-500 uppercase mb-1">QB Online</p>
                            <p className="text-lg font-bold tabular-nums">{formatCurrency(destinationBalance || 0)}</p>
                        </div>
                    </div>

                    {/* Hashes */}
                    {sourceHash && (
                        <div className="space-y-2">
                            <div className="flex items-center justify-between p-2 bg-gray-50 rounded text-xs font-mono">
                                <span className="text-gray-500">Source Hash:</span>
                                <div className="flex items-center gap-2">
                                    <span className="text-gray-700 truncate max-w-[200px]">{sourceHash}</span>
                                    <button
                                        onClick={() => copyToClipboard(sourceHash, "source")}
                                        className="text-gray-400 hover:text-gray-600"
                                    >
                                        {copiedHash === "source" ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
                                    </button>
                                </div>
                            </div>
                            {destinationHash && (
                                <div className="flex items-center justify-between p-2 bg-gray-50 rounded text-xs font-mono">
                                    <span className="text-gray-500">Dest Hash:</span>
                                    <div className="flex items-center gap-2">
                                        <span className="text-gray-700 truncate max-w-[200px]">{destinationHash}</span>
                                        <button
                                            onClick={() => copyToClipboard(destinationHash, "dest")}
                                            className="text-gray-400 hover:text-gray-600"
                                        >
                                            {copiedHash === "dest" ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
                                        </button>
                                    </div>
                                </div>
                            )}
                            {hashMatch !== undefined && (
                                <div className={`text-xs px-2 py-1 rounded ${hashMatch ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                                    {hashMatch ? "✓ Hash chain verified" : "⚠ Hash mismatch detected"}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Expanded Details - Bank Accounts */}
            {expanded && bankAccounts.length > 0 && (
                <div className="border-t border-gray-100 bg-white p-4">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-gray-500">
                                <th className="pb-2 font-medium">Bank Account</th>
                                <th className="pb-2 font-medium">Last Reconciled</th>
                                <th className="pb-2 font-medium">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {bankAccounts.map((account) => (
                                <tr key={account.name} className="border-t border-gray-50">
                                    <td className="py-2 font-medium text-gray-900">{account.name}</td>
                                    <td className="py-2 text-gray-500">{account.lastReconciled || "Never"}</td>
                                    <td className="py-2">
                                        {account.match ? (
                                            <span className="badge badge-success">
                                                <CheckCircle2 className="w-3 h-3 mr-1" />
                                                Matched
                                            </span>
                                        ) : (
                                            <span className="badge badge-warning">
                                                <AlertCircle className="w-3 h-3 mr-1" />
                                                Mismatch
                                            </span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Lead Sheet Breakdown - 58 Standard Codes */}
            {expanded && leadSheetBreakdown.length > 0 && (
                <div className="border-t border-gray-100 bg-white p-4">
                    <div className="flex items-center justify-between mb-3">
                        <h4 className="font-semibold text-gray-900 flex items-center gap-2">
                            <Shield className="w-4 h-4 text-blue-600" />
                            Lead Sheet Reconciliation (58 Codes)
                        </h4>
                        <div className="flex items-center gap-2">
                            <select
                                value={leadSheetFilter}
                                onChange={(e) => setLeadSheetFilter(e.target.value)}
                                className="text-xs border rounded px-2 py-1"
                            >
                                <option value="all">All Categories</option>
                                <option value="Assets">Assets</option>
                                <option value="Liabilities">Liabilities</option>
                                <option value="Equity">Equity</option>
                                <option value="Income">Income</option>
                                <option value="COGS">COGS</option>
                                <option value="Expenses">Expenses</option>
                                <option value="variances">Show Variances Only</option>
                            </select>
                            <button
                                onClick={() => setShowLeadSheet(!showLeadSheet)}
                                className="text-xs text-blue-600 hover:text-blue-800"
                            >
                                {showLeadSheet ? "Hide Details" : "Show Details"}
                            </button>
                        </div>
                    </div>

                    {/* Summary by Category */}
                    <div className="grid grid-cols-6 gap-2 mb-3">
                        {["Assets", "Liabilities", "Equity", "Income", "COGS", "Expenses"].map((category) => {
                            const categoryItems = leadSheetBreakdown.filter(
                                (item) => item.category === category
                            );
                            const matched = categoryItems.filter((item) => item.isMatched).length;
                            const total = categoryItems.length;
                            const allMatched = matched === total;

                            return (
                                <div
                                    key={category}
                                    className={`p-2 rounded text-center text-xs ${
                                        allMatched ? "bg-green-50 border border-green-200" : "bg-yellow-50 border border-yellow-200"
                                    }`}
                                >
                                    <div className="font-medium text-gray-700">{category}</div>
                                    <div className={allMatched ? "text-green-600" : "text-yellow-600"}>
                                        {matched}/{total}
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Total Variance Summary */}
                    <div className={`p-3 rounded-lg mb-3 ${
                        leadSheetBreakdown.every(item => item.isMatched)
                            ? "bg-green-50 border border-green-200"
                            : "bg-yellow-50 border border-yellow-200"
                    }`}>
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">Total Variance Across All 58 Lead Sheets:</span>
                            <span className={`text-lg font-bold ${
                                leadSheetBreakdown.every(item => item.isMatched)
                                    ? "text-green-600"
                                    : "text-yellow-600"
                            }`}>
                                {formatCurrency(leadSheetBreakdown.reduce((sum, item) => sum + Math.abs(item.variance), 0))}
                            </span>
                        </div>
                        {leadSheetBreakdown.every(item => item.isMatched) && (
                            <div className="text-xs text-green-600 mt-1 flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" />
                                All 58 Lead Sheet codes balanced to $0.00
                            </div>
                        )}
                    </div>

                    {/* Detailed Table */}
                    {showLeadSheet && (
                        <div className="max-h-64 overflow-y-auto border rounded">
                            <table className="w-full text-xs">
                                <thead className="bg-gray-50 sticky top-0">
                                    <tr className="text-left text-gray-500">
                                        <th className="p-2 font-medium">Code</th>
                                        <th className="p-2 font-medium">Name</th>
                                        <th className="p-2 font-medium">Category</th>
                                        <th className="p-2 font-medium text-right">Source</th>
                                        <th className="p-2 font-medium text-right">Dest</th>
                                        <th className="p-2 font-medium text-right">Variance</th>
                                        <th className="p-2 font-medium text-center">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {leadSheetBreakdown
                                        .filter((item) => {
                                            if (leadSheetFilter === "all") return true;
                                            if (leadSheetFilter === "variances") return !item.isMatched;
                                            return item.category === leadSheetFilter;
                                        })
                                        .map((item) => (
                                            <tr
                                                key={item.code}
                                                className={`border-t ${
                                                    item.isMatched ? "" : "bg-yellow-50"
                                                }`}
                                            >
                                                <td className="p-2 font-mono font-medium">{item.code}</td>
                                                <td className="p-2 text-gray-700">{item.name}</td>
                                                <td className="p-2 text-gray-500">{item.category}</td>
                                                <td className="p-2 text-right tabular-nums">
                                                    {formatCurrency(item.sourceBalance)}
                                                </td>
                                                <td className="p-2 text-right tabular-nums">
                                                    {formatCurrency(item.destBalance)}
                                                </td>
                                                <td className={`p-2 text-right tabular-nums ${
                                                    item.variance !== 0 ? "text-red-600 font-medium" : "text-green-600"
                                                }`}>
                                                    {formatCurrency(item.variance)}
                                                </td>
                                                <td className="p-2 text-center">
                                                    {item.isMatched ? (
                                                        <CheckCircle2 className="w-4 h-4 text-green-500 mx-auto" />
                                                    ) : (
                                                        <AlertCircle className="w-4 h-4 text-yellow-500 mx-auto" />
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* Footer */}
            {(lastChecked || verificationTimestamp) && (
                <div className="px-4 py-2 bg-white border-t border-gray-100 text-xs text-gray-400">
                    Last verified: {verificationTimestamp || lastChecked}
                </div>
            )}
        </div>
    );
}
