"use client";

import { useParams, useRouter } from "next/navigation";
import { useLiveStatus, useTrialBalance } from "@/lib/hooks/useLiveStatus";
import { useQuery } from "@tanstack/react-query";
import { PizzaTracker } from "@/components/dashboard/PizzaTracker";
import { ReconciliationShield } from "@/components/dashboard/ReconciliationShield";
import { AuditCertCard } from "@/components/dashboard/AuditCertCard";
import { CasewareBundleCard } from "@/components/dashboard/CasewareBundleCard";
import { ForensicIntegrityPulse } from "@/components/dashboard/ForensicIntegrityPulse";
import { DiscrepancyDoctor, Discrepancy } from "@/components/migrations/DiscrepancyDoctor";
import { ArrowLeft, Clock, CheckCircle, AlertCircle, Loader2, Cloud, FileBarChart2 } from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

// Destination type
type DestinationType = "qbo" | "caseware";

// FIX: Define proper types for API responses instead of using 'any'
interface LiveStatusResponse {
    migration_id: string;
    phase: string;
    phase_number: number;
    percentage: number;
    current_entity: string | null;
    status_message: string;
    status: string;
    alerts: string[];
    integrity_verified: boolean;
    phases: Array<{
        name: string;
        status: "pending" | "in_progress" | "completed";
        percentage: number;
        description: string;
    }>;
    company_name: string;
    started_at: string;
    elapsed_seconds: number;
    completed_at?: string;
    duration_seconds?: number;
    error?: string;
    destination?: DestinationType;
}

interface ApiDiscrepancy {
    account_name: string;
    account_type?: string;
    source_balance: number;
    destination_balance: number;
    difference: number;
    severity?: "critical" | "warning" | "info";
    possible_cause?: string;
}

export default function MigrationDetailPage() {
    const params = useParams();
    const router = useRouter();
    const id = params?.id as string;

    // Real API hooks
    const { data: liveStatus, isLoading: statusLoading } = useLiveStatus(id);
    const { data: trialBalance } = useTrialBalance(id, liveStatus?.status === "completed");

    // Fetch discrepancies from API
    const { data: discrepancyData } = useQuery({
        queryKey: ["discrepancies", id],
        queryFn: async () => {
            const token = localStorage.getItem('token');
            const response = await fetch(`${API_URL}/api/migrations/${id}/discrepancies`, {
                credentials: 'include',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            });
            if (!response.ok) return { discrepancies: [], total_discrepancy: 0 };
            return response.json();
        },
        enabled: !!id && liveStatus?.status === "completed",
    });

    // Fetch record count from API
    const { data: recordCountData } = useQuery({
        queryKey: ["recordCount", id],
        queryFn: async () => {
            const token = localStorage.getItem('token');
            const response = await fetch(`${API_URL}/api/migrations/${id}/record-count`, {
                credentials: 'include',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            });
            if (!response.ok) return { record_count: 0 };
            return response.json();
        },
        enabled: !!id,
    });

    // FIX: Remove 'any' cast - use typed response
    // The liveStatus is typed from useLiveStatus hook, destination is optional
    const destination: DestinationType = (liveStatus as LiveStatusResponse | undefined)?.destination || "qbo";

    const [isCancelling, setIsCancelling] = useState(false);
    const [showDiscrepancyDoctor, setShowDiscrepancyDoctor] = useState(true);
    // FIX: Add state for concurrent request throttling
    const [isExportingReport, setIsExportingReport] = useState(false);

    // FIX: Improved error messages with specific details
    const handleExportDiscrepancyReport = async () => {
        // FIX: Prevent concurrent requests
        if (isExportingReport) return;
        setIsExportingReport(true);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'}/api/migrations/${id}/discrepancy-report`, {
                credentials: 'include',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            });
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Discrepancy_Report_${id}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                // FIX: Provide specific error details based on HTTP status
                let errorMessage = "Failed to export discrepancy report.";
                if (response.status === 401) {
                    errorMessage += " Your session may have expired. Please log in again.";
                } else if (response.status === 404) {
                    errorMessage += " The report was not found for this migration.";
                } else if (response.status === 403) {
                    errorMessage += " You don't have permission to access this report.";
                } else if (response.status >= 500) {
                    errorMessage += ` Server error (${response.status}). Please try again later.`;
                } else {
                    try {
                        const errorData = await response.json();
                        if (errorData.error) {
                            errorMessage = errorData.error;
                        }
                    } catch {
                        // Response wasn't JSON
                    }
                }
                alert(errorMessage);
            }
        } catch (error) {
            console.error("Export error:", error);
            // FIX: Differentiate between network errors and other errors
            if (error instanceof TypeError && error.message.includes('fetch')) {
                alert("Network error: Unable to connect to the server. Please check your internet connection.");
            } else {
                alert("Failed to export report. Please try again.");
            }
        } finally {
            // FIX: Always reset loading state
            setIsExportingReport(false);
        }
    };

    const handleReviewResolve = () => {
        // Navigate to reports page where discrepancies can be reviewed
        router.push('/reports');
    };

    const handleCancelMigration = async () => {
        if (!confirm("Are you sure you want to cancel this migration?")) return;
        setIsCancelling(true);
        try {
            const result = await api.cancelMigration(id);
            if (result.success) {
                router.refresh();
            } else {
                alert(result.error || "Failed to cancel migration");
            }
        } catch (error) {
            console.error("Cancel error:", error);
            alert("Failed to cancel migration");
        } finally {
            setIsCancelling(false);
        }
    };

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

    const getDestinationBadge = () => {
        if (destination === "caseware") {
            return (
                <span className="flex items-center gap-1 px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                    <FileBarChart2 className="w-4 h-4" />
                    Caseware
                </span>
            );
        }
        return (
            <span className="flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
                <Cloud className="w-4 h-4" />
                QuickBooks Online
            </span>
        );
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
    const isCaseware = destination === "caseware";

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
                        <div className="flex items-center gap-3">
                            {getStatusIcon()}
                            <h1 className="text-2xl font-bold text-gray-900">
                                {liveStatus?.company_name || "Migration Details"}
                            </h1>
                            {getDestinationBadge()}
                        </div>
                        <p className="text-sm text-gray-500 mt-1">
                            Session ID: <code className="text-[var(--bridge-blue)]">{id}</code>
                            {isCaseware && <span className="ml-2 text-purple-600">• Caseware Audit Bundle Mode</span>}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {isProcessing && (
                        <button
                            className="flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            onClick={handleCancelMigration}
                            disabled={isCancelling}
                        >
                            {isCancelling ? "Cancelling..." : "Cancel Migration"}
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
                sourceBalance={trialBalance?.source_trial_balance ?? undefined}
                destinationBalance={trialBalance?.destination_trial_balance ?? undefined}
                discrepancy={trialBalance?.discrepancy ?? 0}
                isBalanced={trialBalance?.is_balanced ?? (isCompleted && !discrepancyData?.has_discrepancies)}
                forensicStatus={
                    (trialBalance?.forensic_status as "VERIFIED" | "PENDING" | "DISCREPANCY_DETECTED" | "NOT_AVAILABLE") ||
                    (isCompleted ? "VERIFIED" : "PENDING")
                }
                verificationTimestamp={trialBalance?.verification_timestamp ?? undefined}
                sourceHash={trialBalance?.source_hash ?? undefined}
                destinationHash={trialBalance?.destination_hash ?? undefined}
                hashMatch={trialBalance?.hash_match ?? undefined}
                migrationId={id}
                isLoading={!isCompleted && statusLoading}
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
                    recordCount={recordCountData?.record_count || 0}
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
            {(discrepancyData?.has_discrepancies && showDiscrepancyDoctor) ? (
                <DiscrepancyDoctor
                    discrepancies={discrepancyData.discrepancies.map((d: ApiDiscrepancy) => ({
                        account_name: d.account_name,
                        account_type: d.account_type || "Unknown",
                        source_balance: d.source_balance,
                        destination_balance: d.destination_balance,
                        difference: d.difference,
                        severity: d.severity || "warning",
                        possible_cause: d.possible_cause,
                    }))}
                    totalDiscrepancy={discrepancyData.total_discrepancy}
                    onDismiss={() => setShowDiscrepancyDoctor(false)}
                    onExportReport={handleExportDiscrepancyReport}
                    onReviewResolve={handleReviewResolve}
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
