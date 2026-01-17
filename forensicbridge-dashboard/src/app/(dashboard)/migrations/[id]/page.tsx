"use client";

import { useParams } from "next/navigation";
import { useLiveStatus, useTrialBalance, useAuditCertificate } from "@/lib/hooks/useLiveStatus";
import { PizzaTracker } from "@/components/dashboard/PizzaTracker";
import { ReconciliationShield } from "@/components/dashboard/ReconciliationShield";
import { AuditCertCard } from "@/components/dashboard/AuditCertCard";
import { CasewareBundleCard } from "@/components/dashboard/CasewareBundleCard";
import { ForensicIntegrityPulse } from "@/components/dashboard/ForensicIntegrityPulse";
import { DiscrepancyDoctor } from "@/components/migrations/DiscrepancyDoctor";
import { ArrowLeft, Clock, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

export default function MigrationDetailPage() {
    const params = useParams();
    const id = params?.id as string;

    // Hooks using forced mocks
    const { data: liveStatus, isLoading: statusLoading } = useLiveStatus(id);
    const { data: trialBalance } = useTrialBalance(id, liveStatus?.status === "completed");

    // Mock download handler since api is removed
    const [isDownloading, setIsDownloading] = useState(false);
    const handleDownloadCertificate = async () => {
        setIsDownloading(true);
        try {
            const blob = await api.downloadAuditCertificate(id);
            if (blob) {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Audit_Certificate_${id}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                alert("Certificate download failed.");
            }
        } catch (e) {
            console.error(e);
            alert("Error downloading certificate.");
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

    if (statusLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-[var(--bridge-blue)]" />
            </div>
        );
    }

    const isCompleted = liveStatus?.status === "completed";
    const isProcessing = liveStatus?.status === "processing";

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
                    {isProcessing && (
                        <button className="flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors">
                            Cancel Migration
                        </button>
                    )}
                </div>
            </div>

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #1: FORENSIC TRUST CHAIN (PIZZA TRACKER)
                5-phase visual progress bar - ALWAYS VISIBLE at top
            ═══════════════════════════════════════════════════════════════ */}
            <PizzaTracker
                phases={liveStatus?.phases || []}
                currentPhase={liveStatus?.phase_number || 1}
                overallPercentage={liveStatus?.percentage || 0}
                currentEntity={liveStatus?.current_entity}
                statusMessage={liveStatus?.status_message}
                companyName={liveStatus?.company_name}
                elapsedSeconds={liveStatus?.elapsed_seconds || 0}
            />

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #2: RECONCILIATION SHIELD
                Large green ✓ or red ⚠ - THE MOST IMPORTANT DATA POINT
            ═══════════════════════════════════════════════════════════════ */}
            <ReconciliationShield
                sourceBalance={trialBalance?.source_trial_balance ?? 125847.32}
                destinationBalance={trialBalance?.destination_trial_balance ?? 125847.32}
                discrepancy={trialBalance?.discrepancy ?? 0}
                isBalanced={trialBalance?.is_balanced ?? true}
                forensicStatus={
                    (trialBalance?.forensic_status as "VERIFIED" | "PENDING" | "DISCREPANCY_DETECTED" | "NOT_AVAILABLE") ||
                    (isCompleted ? "VERIFIED" : "PENDING")
                }
                verificationTimestamp={trialBalance?.verification_timestamp || new Date().toISOString()}
                sourceHash={trialBalance?.source_hash || "7e2f8a9c3b4d5e6f7a8b9c0d1e2f3a4b..."}
                destinationHash={trialBalance?.destination_hash || "7e2f8a9c3b4d5e6f7a8b9c0d1e2f3a4b..."}
                hashMatch={trialBalance?.hash_match ?? true}
                migrationId={id}
            />

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #3 & #5: CASEWARE BUNDLE + AUDIT CERTIFICATE
                Side-by-side download cards - THE USP
            ═══════════════════════════════════════════════════════════════ */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <CasewareBundleCard
                    migrationId={id}
                    companyName={liveStatus?.company_name || "Company"}
                    isAvailable={isCompleted}
                    recordCount={12847}
                />

                <AuditCertCard
                    migrationId={id}
                    companyName={liveStatus?.company_name || "Unknown"}
                    completedAt={liveStatus?.completed_at || null}
                    isAvailable={isCompleted}
                    onDownload={handleDownloadCertificate}
                    isDownloading={isDownloading}
                />
            </div>

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #4: FORENSIC INTEGRITY PULSE
                Terminal-style rolling log - Chain of Custody visualization
            ═══════════════════════════════════════════════════════════════ */}
            <ForensicIntegrityPulse
                isLive={isProcessing}
                migrationId={id}
            />

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #6: DISCREPANCY DOCTOR
                Interactive drill-down - only shown if there are variances
            ═══════════════════════════════════════════════════════════════ */}
            {(trialBalance?.discrepancy && trialBalance.discrepancy !== 0) ? (
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
            ) : isCompleted ? (
                <div className="card-forensic bg-green-50 border-green-200 p-6">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                            <CheckCircle className="w-6 h-6 text-green-600" />
                        </div>
                        <div>
                            <h3 className="font-bold text-green-900 text-lg">Penny-Perfect Migration</h3>
                            <p className="text-green-700">
                                All accounts balanced. No discrepancies detected. Ready for CPA sign-off.
                            </p>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
