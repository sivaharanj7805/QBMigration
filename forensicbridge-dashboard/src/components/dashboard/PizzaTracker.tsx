"use client";

import { Database, Upload, Shuffle, ShieldCheck, Check, Loader2 } from "lucide-react";

interface Phase {
    name: string;
    status: "pending" | "in_progress" | "completed";
    percentage: number;
    description: string;
}

interface PizzaTrackerProps {
    phases: Phase[];
    currentPhase: number;
    overallPercentage: number;
    currentEntity?: string | null;
    statusMessage?: string;
    companyName?: string;
    elapsedSeconds?: number;
}

const phaseIcons = {
    EXTRACTION: Database,
    TRANSIT: Upload,
    TRANSFORMATION: Shuffle,
    VERIFICATION: ShieldCheck,
};

const phaseLabels = {
    EXTRACTION: "Secure Extraction",
    TRANSIT: "Encrypted Transit",
    TRANSFORMATION: "Multi-Core Transformation",
    VERIFICATION: "Forensic Certification",
};

const phaseDescriptions = {
    EXTRACTION: "STA Thread Locked. Extracting 55 Entity Types...",
    TRANSIT: "AES-256-GCM Stream Active. Uploading to S3...",
    TRANSFORMATION: "Parallel Reconstruction: Rebuilding Linked Transactions...",
    VERIFICATION: "Verifying SHA-256 Hash Chain...",
};

export function PizzaTracker({
    phases,
    currentPhase: _currentPhase,
    overallPercentage: rawPercentage,
    currentEntity,
    statusMessage,
    companyName,
    elapsedSeconds = 0,
}: PizzaTrackerProps) {
    // LOW-08 FIX: Clamp percentage to 0-100 range
    const overallPercentage = Math.min(100, Math.max(0, rawPercentage));
    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    };

    return (
        <div className="card-forensic p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h2 className="text-lg font-semibold text-gray-900">Forensic Trust Chain</h2>
                    {companyName && (
                        <p className="text-sm text-gray-500">Processing: {companyName}</p>
                    )}
                </div>
                <div className="text-right">
                    <p className="text-2xl font-bold tabular-nums text-[var(--bridge-blue)]">
                        {overallPercentage}%
                    </p>
                    <p className="text-xs text-gray-500">
                        Elapsed: {formatTime(elapsedSeconds)}
                    </p>
                    {/* AUDIT FIX LOW-3: Show estimated time remaining */}
                    {overallPercentage > 5 && overallPercentage < 100 && elapsedSeconds > 0 && (
                        <p className="text-xs text-gray-400">
                            ETA: ~{formatTime(
                                Math.round((elapsedSeconds / overallPercentage) * (100 - overallPercentage))
                            )}
                        </p>
                    )}
                </div>
            </div>

            {/* Overall Progress Bar - FIX: Added ARIA attributes for accessibility */}
            <div
                className="progress-bar mb-8"
                role="progressbar"
                aria-valuenow={overallPercentage}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Migration progress: ${overallPercentage}% complete`}
            >
                <div
                    className={`progress-bar-fill ${overallPercentage >= 100 ? "success" : ""}`}
                    style={{ width: `${overallPercentage}%` }}
                />
            </div>

            {/* 4-Phase Stepper */}
            <div className="flex items-start justify-between">
                {phases.map((phase, index) => {
                    const Icon = phaseIcons[phase.name as keyof typeof phaseIcons] || Database;
                    const label = phaseLabels[phase.name as keyof typeof phaseLabels] || phase.name;
                    const description = phase.description ||
                        phaseDescriptions[phase.name as keyof typeof phaseDescriptions] || "";

                    return (
                        <div key={phase.name} className="flex items-start flex-1">
                            {/* Phase Node */}
                            <div className="stepper-phase flex-1">
                                <div className={`stepper-icon ${phase.status}`}>
                                    {phase.status === "completed" ? (
                                        <Check className="w-6 h-6" />
                                    ) : phase.status === "in_progress" ? (
                                        <Loader2 className="w-6 h-6 animate-spin" />
                                    ) : (
                                        <Icon className="w-6 h-6" />
                                    )}
                                </div>

                                <div className="mt-3 text-center">
                                    <p className={`text-sm font-medium ${phase.status === "completed"
                                        ? "text-[var(--success)]"
                                        : phase.status === "in_progress"
                                            ? "text-[var(--bridge-blue)]"
                                            : "text-gray-400"
                                        }`}>
                                        {label}
                                    </p>

                                    {phase.status === "in_progress" && (
                                        <p className="text-xs text-gray-500 mt-1 max-w-[150px] mx-auto">
                                            {statusMessage || description}
                                        </p>
                                    )}

                                    {phase.status === "in_progress" && currentEntity && (
                                        <p className="text-xs text-[var(--bridge-blue)] mt-1 font-medium">
                                            {currentEntity}
                                        </p>
                                    )}

                                    {phase.status === "in_progress" && (
                                        <div className="mt-2 w-24 mx-auto">
                                            {/* FIX: Added ARIA attributes to phase progress bar */}
                                            <div
                                                className="progress-bar h-1"
                                                role="progressbar"
                                                aria-valuenow={phase.percentage}
                                                aria-valuemin={0}
                                                aria-valuemax={100}
                                                aria-label={`${label} progress: ${Math.round(phase.percentage)}%`}
                                            >
                                                <div
                                                    className="progress-bar-fill"
                                                    style={{ width: `${phase.percentage}%` }}
                                                />
                                            </div>
                                            <p className="text-xs text-gray-400 mt-1">{Math.round(phase.percentage)}%</p>
                                        </div>
                                    )}

                                    {phase.status === "completed" && (
                                        <p className="text-xs text-[var(--success)] mt-1">✓ Verified</p>
                                    )}
                                </div>
                            </div>

                            {/* Connector Line */}
                            {index < phases.length - 1 && (
                                <div
                                    className={`stepper-connector mt-6 ${phase.status === "completed"
                                        ? "completed"
                                        : phase.status === "in_progress"
                                            ? "active"
                                            : ""
                                        }`}
                                />
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
