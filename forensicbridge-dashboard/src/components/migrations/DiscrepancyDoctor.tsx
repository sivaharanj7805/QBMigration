"use client";

import { AlertTriangle, XCircle, HelpCircle, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

export interface Discrepancy {
    account_name: string;
    account_type: string;
    source_balance: number;
    destination_balance: number;
    difference: number;
    severity: "critical" | "warning" | "info";
    possible_cause?: string;
}

interface DiscrepancyDoctorProps {
    discrepancies: Discrepancy[];
    totalDiscrepancy: number;
    onDismiss?: () => void;
    onExportReport?: () => void;
    onReviewResolve?: () => void;
}

export function DiscrepancyDoctor({
    discrepancies,
    totalDiscrepancy,
    onDismiss,
    onExportReport,
    onReviewResolve,
}: DiscrepancyDoctorProps) {
    const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

    const toggleRow = (index: number) => {
        const newExpanded = new Set(expandedRows);
        if (newExpanded.has(index)) {
            newExpanded.delete(index);
        } else {
            newExpanded.add(index);
        }
        setExpandedRows(newExpanded);
    };

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2,
        }).format(amount);
    };

    const getSeverityIcon = (severity: string) => {
        switch (severity) {
            case "critical":
                return <XCircle className="w-4 h-4 text-[var(--error)]" />;
            case "warning":
                return <AlertTriangle className="w-4 h-4 text-[var(--forensic-gold)]" />;
            default:
                return <HelpCircle className="w-4 h-4 text-[var(--bridge-blue)]" />;
        }
    };

    const getSeverityClass = (severity: string) => {
        switch (severity) {
            case "critical":
                return "bg-red-50 border-red-200";
            case "warning":
                return "bg-yellow-50 border-yellow-200";
            default:
                return "bg-blue-50 border-blue-200";
        }
    };

    if (discrepancies.length === 0) {
        return null;
    }

    return (
        <div className="card-forensic border-2 border-[var(--error)] overflow-hidden">
            {/* Alert Header */}
            <div className="bg-red-50 px-6 py-4 border-b border-red-100">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                            <AlertTriangle className="w-5 h-5 text-[var(--error)]" />
                        </div>
                        <div>
                            <h3 className="font-semibold text-gray-900">
                                Trial Balance Mismatch Detected
                            </h3>
                            <p className="text-sm text-gray-600">
                                Total Discrepancy:{" "}
                                <span className="font-bold text-[var(--error)]">
                                    {formatCurrency(totalDiscrepancy)}
                                </span>
                            </p>
                        </div>
                    </div>
                    {onDismiss && (
                        <button
                            onClick={onDismiss}
                            className="text-gray-400 hover:text-gray-600"
                        >
                            <XCircle className="w-5 h-5" />
                        </button>
                    )}
                </div>
            </div>

            {/* Discrepancy Details */}
            <div className="p-4 space-y-2">
                <p className="text-sm text-gray-500 mb-4">
                    The following accounts show differences between QuickBooks Desktop and
                    QuickBooks Online:
                </p>

                {discrepancies.map((discrepancy, index) => (
                    <div
                        key={index}
                        className={`rounded-lg border ${getSeverityClass(discrepancy.severity)}`}
                    >
                        {/* Row Header */}
                        <button
                            onClick={() => toggleRow(index)}
                            className="w-full px-4 py-3 flex items-center justify-between text-left"
                        >
                            <div className="flex items-center gap-3">
                                {getSeverityIcon(discrepancy.severity)}
                                <div>
                                    <span className="font-medium text-gray-900">
                                        {discrepancy.account_name}
                                    </span>
                                    <span className="text-xs text-gray-500 ml-2">
                                        ({discrepancy.account_type})
                                    </span>
                                </div>
                            </div>
                            <div className="flex items-center gap-4">
                                <span
                                    className={`font-bold tabular-nums ${discrepancy.difference < 0
                                            ? "text-[var(--error)]"
                                            : "text-[var(--success)]"
                                        }`}
                                >
                                    {discrepancy.difference > 0 ? "+" : ""}
                                    {formatCurrency(discrepancy.difference)}
                                </span>
                                {expandedRows.has(index) ? (
                                    <ChevronDown className="w-4 h-4 text-gray-400" />
                                ) : (
                                    <ChevronRight className="w-4 h-4 text-gray-400" />
                                )}
                            </div>
                        </button>

                        {/* Expanded Details */}
                        {expandedRows.has(index) && (
                            <div className="px-4 pb-4 pt-0 border-t border-gray-200 mt-0">
                                <div className="grid grid-cols-2 gap-4 mt-3">
                                    <div className="p-3 bg-white rounded border">
                                        <p className="text-xs text-gray-500 mb-1">Desktop (Source)</p>
                                        <p className="font-bold tabular-nums">
                                            {formatCurrency(discrepancy.source_balance)}
                                        </p>
                                    </div>
                                    <div className="p-3 bg-white rounded border">
                                        <p className="text-xs text-gray-500 mb-1">Online (Destination)</p>
                                        <p className="font-bold tabular-nums">
                                            {formatCurrency(discrepancy.destination_balance)}
                                        </p>
                                    </div>
                                </div>

                                {discrepancy.possible_cause && (
                                    <div className="mt-3 p-3 bg-white rounded border">
                                        <p className="text-xs text-gray-500 mb-1">Possible Cause</p>
                                        <p className="text-sm text-gray-700">
                                            {discrepancy.possible_cause}
                                        </p>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Actions */}
            <div className="px-6 py-4 bg-gray-50 border-t flex items-center justify-end gap-3">
                <button
                    onClick={onExportReport}
                    disabled={!onExportReport}
                    className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Export Report
                </button>
                <button
                    onClick={onReviewResolve}
                    disabled={!onReviewResolve}
                    className="px-4 py-2 text-sm font-medium text-white bg-[var(--bridge-blue)] hover:bg-[var(--bridge-blue)]/90 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Review & Resolve
                </button>
            </div>
        </div>
    );
}
