"use client";

import { Shield, CheckCircle, AlertTriangle, XCircle, Trophy, Download } from "lucide-react";

interface ReconciliationShieldProps {
    sourceBalance: number | null;
    destinationBalance: number | null;
    discrepancy: number | null;
    isBalanced: boolean | null;
    forensicStatus: "VERIFIED" | "PENDING" | "DISCREPANCY_DETECTED" | "NOT_AVAILABLE";
    verificationTimestamp?: string | null;
    sourceHash?: string;
    destinationHash?: string;
    hashMatch?: boolean;
    onDownloadCertificate?: () => void;
    migrationId?: string;
}

export function ReconciliationShield({
    sourceBalance,
    destinationBalance,
    discrepancy,
    isBalanced,
    forensicStatus,
    verificationTimestamp,
    sourceHash,
    destinationHash,
    hashMatch,
    onDownloadCertificate,
    migrationId,
}: ReconciliationShieldProps) {
    const formatCurrency = (amount: number | null) => {
        if (amount === null) return "—";
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2,
        }).format(amount);
    };

    const formatTimestamp = (ts: string | null | undefined) => {
        if (!ts) return "—";
        return new Date(ts).toLocaleString("en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    };

    const getStatusClass = () => {
        if (forensicStatus === "VERIFIED" && isBalanced) return "balanced";
        if (forensicStatus === "DISCREPANCY_DETECTED") return "discrepancy";
        return "";
    };

    const getStatusBadge = () => {
        switch (forensicStatus) {
            case "VERIFIED":
                return (
                    <div className="gold-badge">
                        <Trophy className="w-4 h-4" />
                        PENNY-PERFECT MATCH
                    </div>
                );
            case "PENDING":
                return (
                    <div className="badge-processing flex items-center gap-1">
                        <Shield className="w-3 h-3" />
                        Verification Pending
                    </div>
                );
            case "DISCREPANCY_DETECTED":
                return (
                    <div className="badge-error flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />
                        Discrepancy Detected
                    </div>
                );
            default:
                return (
                    <div className="badge-warning flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />
                        Not Available
                    </div>
                );
        }
    };

    return (
        <div className={`reconciliation-shield ${getStatusClass()}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--forensic-gold)] to-[var(--bridge-blue)] flex items-center justify-center">
                        <Shield className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900">Reconciliation Shield</h2>
                        <p className="text-xs text-gray-500">Trial Balance Verification</p>
                    </div>
                </div>
                {getStatusBadge()}
            </div>

            {/* Trial Balance Comparison */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {/* Source (QBDT) */}
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                        QuickBooks Desktop
                    </p>
                    <p className="text-2xl font-bold tabular-nums text-gray-900">
                        {formatCurrency(sourceBalance)}
                    </p>
                    {sourceBalance !== null && (
                        <div className="flex items-center justify-center gap-1 mt-2">
                            <CheckCircle className="w-4 h-4 text-[var(--success)]" />
                            <span className="text-xs text-[var(--success)]">Verified</span>
                        </div>
                    )}
                </div>

                {/* Destination (QBO) */}
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                        QuickBooks Online
                    </p>
                    <p className="text-2xl font-bold tabular-nums text-gray-900">
                        {formatCurrency(destinationBalance)}
                    </p>
                    {destinationBalance !== null && (
                        <div className="flex items-center justify-center gap-1 mt-2">
                            <CheckCircle className="w-4 h-4 text-[var(--success)]" />
                            <span className="text-xs text-[var(--success)]">Verified</span>
                        </div>
                    )}
                </div>

                {/* Delta */}
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                        Discrepancy
                    </p>
                    <p className={`text-2xl font-bold tabular-nums ${discrepancy === 0
                            ? "text-[var(--success)]"
                            : discrepancy !== null
                                ? "text-[var(--error)]"
                                : "text-gray-400"
                        }`}>
                        {discrepancy !== null ? formatCurrency(discrepancy) : "—"}
                    </p>
                    {discrepancy === 0 && (
                        <div className="flex items-center justify-center gap-1 mt-2">
                            <CheckCircle className="w-4 h-4 text-[var(--success)]" />
                            <span className="text-xs text-[var(--success)]">Match</span>
                        </div>
                    )}
                    {discrepancy !== null && discrepancy !== 0 && (
                        <div className="flex items-center justify-center gap-1 mt-2">
                            <XCircle className="w-4 h-4 text-[var(--error)]" />
                            <span className="text-xs text-[var(--error)]">Mismatch</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Hash Verification */}
            {(sourceHash || destinationHash) && (
                <div className="border-t border-gray-200 pt-4 mb-4">
                    <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                            <span className="text-gray-500">SHA-256:</span>
                            <code className="text-forensic-gold font-mono">{sourceHash || "—"}</code>
                        </div>
                        {hashMatch !== undefined && (
                            <div className={`flex items-center gap-1 ${hashMatch ? "text-[var(--success)]" : "text-[var(--error)]"}`}>
                                {hashMatch ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                                <span>{hashMatch ? "Hash Match" : "Hash Mismatch"}</span>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-gray-200 pt-4">
                <div className="text-xs text-gray-500">
                    <span>Verified: </span>
                    <span className="text-gray-700">{formatTimestamp(verificationTimestamp)}</span>
                    {migrationId && (
                        <>
                            <span className="mx-2">|</span>
                            <span>Session: </span>
                            <code className="text-[var(--bridge-blue)]">{migrationId}</code>
                        </>
                    )}
                </div>

                {forensicStatus === "VERIFIED" && onDownloadCertificate && (
                    <button
                        onClick={onDownloadCertificate}
                        className="flex items-center gap-2 px-4 py-2 bg-[var(--bridge-blue)] text-white text-sm font-medium rounded-lg hover:bg-[var(--bridge-blue)]/90 transition-colors"
                    >
                        <Download className="w-4 h-4" />
                        Download Audit Certificate
                    </button>
                )}
            </div>
        </div>
    );
}
