"use client";

import { Shield, CheckCircle2, AlertCircle, Clock, ChevronDown, Copy, Check } from "lucide-react";
import { useState } from "react";

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
    bankAccounts = [],
    overallStatus,
    lastChecked,
    isLoading = false
}: ReconciliationShieldProps) {
    const [expanded, setExpanded] = useState(false);
    const [copiedHash, setCopiedHash] = useState<"source" | "dest" | null>(null);

    const formatCurrency = (amount: number) => {
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
            <button
                className={`w-full p-4 flex items-center justify-between text-left ${config.bg}`}
                onClick={() => setExpanded(!expanded)}
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

            {/* Footer */}
            {(lastChecked || verificationTimestamp) && (
                <div className="px-4 py-2 bg-white border-t border-gray-100 text-xs text-gray-400">
                    Last verified: {verificationTimestamp || lastChecked}
                </div>
            )}
        </div>
    );
}
