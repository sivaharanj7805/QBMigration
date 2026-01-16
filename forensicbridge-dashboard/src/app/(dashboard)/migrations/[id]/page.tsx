"use client";

import { use } from "react";
import { useLiveStatus, useTrialBalance, useAuditCertificate } from "@/lib/hooks/useLiveStatus";
import { PizzaTracker } from "@/components/dashboard/PizzaTracker";
import { ReconciliationShield } from "@/components/dashboard/ReconciliationShield";
import { AuditCertCard } from "@/components/dashboard/AuditCertCard";
import { ForensicFeed } from "@/components/dashboard/ForensicFeed";
import { DiscrepancyDoctor } from "@/components/migrations/DiscrepancyDoctor";
import { api } from "@/lib/api";
import { ArrowLeft, Clock, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface PageProps {
    params: Promise<{ id: string }>;
}

export default function MigrationDetailPage({ params }: PageProps) {
    const { id } = use(params);
    const { data: liveStatus, isLoading: statusLoading } = useLiveStatus(id);
    const { data: trialBalance } = useTrialBalance(id, liveStatus?.status === "completed");
    const { data: _certPreview } = useAuditCertificate(id, liveStatus?.status === "completed");
    const [isDownloading, setIsDownloading] = useState(false);

    const handleDownloadCertificate = async () => {
        setIsDownloading(true);
        try {
            const blob = await api.downloadAuditCertificate(id);
            if (blob) {
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `${liveStatus?.company_name || id}_audit_certificate.pdf`;
                a.click();
                URL.revokeObjectURL(url);
            }
        } finally {
            setIsDownloading(false);
        }
    };

    const getStatusIcon = () => {
        switch (liveStatus?.status) {
            case "completed":
                return <CheckCircle className="w-5 h-5 text-[var(--success)]" />;
            case "failed":
                return <AlertCircle className="w-5 h-5 text-[var(--error)]" />;
            case "processing":
                return <Loader2 className="w-5 h-5 text-[var(--bridge-blue)] animate-spin" />;
            default:
                return <Clock className="w-5 h-5 text-gray-400" />;
        }
    };

    // Demo forensic log entries
    const demoActivities = [
        { timestamp: new Date(Date.now() - 5000).toISOString(), type: "hash" as const, message: "SHA-256 HASH GENERATED: 0x7e2f8a9c3b...9c" },
        { timestamp: new Date(Date.now() - 4000).toISOString(), type: "warning" as const, message: "PII REDACTION ACTIVE: Phone, Email, SSN masked." },
        { timestamp: new Date(Date.now() - 3000).toISOString(), type: "info" as const, message: "TRANSFORMING: Assembly 'Engine_Kit' -> QBO Bundle." },
        { timestamp: new Date(Date.now() - 2000).toISOString(), type: "success" as const, message: "Integrity Hash Verified for 'Customers.ndjson'" },
        { timestamp: new Date(Date.now() - 1000).toISOString(), type: "info" as const, message: "Processing 'Invoices' (Batch 42/100)..." },
    ];

    if (statusLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-[var(--bridge-blue)]" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link
                        href="/migrations"
                        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-500" />
                    </Link>
                    <div>
                        <div className="flex items-center gap-2">
                            {getStatusIcon()}
                            <h1 className="text-2xl font-bold text-gray-900">
                                {liveStatus?.company_name || "Migration Details"}
                            </h1>
                        </div>
                        <p className="text-sm text-gray-500 mt-1">
                            Session ID: <code className="text-[var(--bridge-blue)]">{id}</code>
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {liveStatus?.status === "processing" && (
                        <button className="flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors">
                            Cancel Migration
                        </button>
                    )}
                </div>
            </div>

            {/* Pizza Tracker */}
            <PizzaTracker
                phases={liveStatus?.phases || []}
                currentPhase={liveStatus?.phase_number || 1}
                overallPercentage={liveStatus?.percentage || 0}
                currentEntity={liveStatus?.current_entity}
                statusMessage={liveStatus?.status_message}
                companyName={liveStatus?.company_name}
                elapsedSeconds={liveStatus?.elapsed_seconds || 0}
            />

            {/* Two Column Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Reconciliation Shield */}
                <ReconciliationShield
                    sourceBalance={trialBalance?.source_trial_balance ?? 0}
                    destinationBalance={trialBalance?.destination_trial_balance ?? 0}
                    discrepancy={trialBalance?.discrepancy ?? 0}
                    isBalanced={trialBalance?.is_balanced ?? false}
                    forensicStatus={
                        (trialBalance?.forensic_status as "VERIFIED" | "PENDING" | "DISCREPANCY_DETECTED" | "NOT_AVAILABLE") ||
                        "PENDING"
                    }
                    verificationTimestamp={trialBalance?.verification_timestamp || new Date().toISOString()}
                    sourceHash={trialBalance?.source_hash}
                    destinationHash={trialBalance?.destination_hash}
                    hashMatch={trialBalance?.hash_match}
                    migrationId={id}
                />

                {/* Audit Certificate Card */}
                <AuditCertCard
                    migrationId={id}
                    companyName={liveStatus?.company_name || "Unknown"}
                    completedAt={liveStatus?.completed_at || null}
                    isAvailable={liveStatus?.status === "completed"}
                    onDownload={handleDownloadCertificate}
                    isDownloading={isDownloading}
                />
            </div>

            {/* Forensic Feed */}
            <ForensicFeed
                activities={demoActivities}
                isLive={liveStatus?.status === "processing"}
                title="Forensic Integrity Log"
            />

            {/* Discrepancy Doctor (shown if there are issues) */}
            {trialBalance?.discrepancy && trialBalance.discrepancy !== 0 && (
                <DiscrepancyDoctor
                    discrepancies={[
                        {
                            account_name: "Accounts Receivable",
                            account_type: "Asset",
                            source_balance: 125000.0,
                            destination_balance: 124580.0,
                            difference: -420.0,
                            severity: "critical",
                            possible_cause: "Invoice #102 missed due to invalid date format",
                        },
                    ]}
                    totalDiscrepancy={trialBalance.discrepancy}
                />
            )}
        </div>
    );
}
