"use client";

import { useState, useCallback } from "react";
import {
    Upload,
    FileSpreadsheet,
    CheckCircle2,
    AlertCircle,
    X,
    HardDrive,
    ArrowRight,
    Shield,
    Clock
} from "lucide-react";

interface UploadedFile {
    name: string;
    size: number;
    type: string;
    status: "pending" | "validating" | "ready" | "error";
    error?: string;
    records?: number;
}

const supportedFormats = [
    { ext: ".QBW", name: "QuickBooks Company File", description: "Primary data file (recommended)" },
    { ext: ".QBB", name: "QuickBooks Backup", description: "Backup file format" },
    { ext: ".QBM", name: "QuickBooks Portable", description: "Smaller portable file" },
    { ext: ".IIF", name: "Intuit Interchange Format", description: "Tab-delimited export" },
    { ext: ".CSV", name: "QuickBooks CSV Export", description: "Comma-separated values" },
    { ext: ".XLSX", name: "QuickBooks Excel Export", description: "Excel spreadsheet format" },
];

export default function UploadPage() {
    const [isDragActive, setIsDragActive] = useState(false);
    const [files, setFiles] = useState<UploadedFile[]>([]);
    const [isProcessing, setIsProcessing] = useState(false);

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setIsDragActive(true);
        } else if (e.type === "dragleave") {
            setIsDragActive(false);
        }
    }, []);

    const processFile = (file: File) => {
        const uploadedFile: UploadedFile = {
            name: file.name,
            size: file.size,
            type: file.name.split('.').pop()?.toUpperCase() || "UNKNOWN",
            status: "validating"
        };

        setFiles(prev => [...prev, uploadedFile]);

        // Simulate validation
        setTimeout(() => {
            setFiles(prev => prev.map(f =>
                f.name === file.name
                    ? { ...f, status: "ready", records: Math.floor(Math.random() * 50000) + 5000 }
                    : f
            ));
        }, 1500);
    };

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragActive(false);

        const droppedFiles = Array.from(e.dataTransfer.files);
        droppedFiles.forEach(processFile);
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFiles = Array.from(e.target.files || []);
        selectedFiles.forEach(processFile);
    };

    const removeFile = (name: string) => {
        setFiles(prev => prev.filter(f => f.name !== name));
    };

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    };

    const readyFiles = files.filter(f => f.status === "ready");

    const handleStartMigration = () => {
        setIsProcessing(true);
        // Would trigger actual migration
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Upload Files</h1>
                <p className="text-gray-500 mt-1">Upload QuickBooks files for migration or analysis</p>
            </div>

            {/* Drag & Drop Zone */}
            <div
                className={`drop-zone ${isDragActive ? "active" : ""}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
            >
                <div className="w-16 h-16 mx-auto bg-blue-50 rounded-full flex items-center justify-center mb-4">
                    <Upload className="w-8 h-8 text-[var(--bridge-blue)]" />
                </div>
                <p className="text-lg font-medium text-gray-700 mb-1">
                    Drag & Drop your QuickBooks files here
                </p>
                <p className="text-sm text-gray-400 mb-4">or click to browse</p>
                <label className="btn-primary cursor-pointer">
                    Select Files
                    <input
                        type="file"
                        accept=".qbw,.qbb,.qbm,.iif,.csv,.xlsx"
                        multiple
                        className="hidden"
                        onChange={handleFileSelect}
                    />
                </label>
            </div>

            {/* Uploaded Files */}
            {files.length > 0 && (
                <div className="card-forensic">
                    <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                        <h2 className="font-semibold text-gray-900">Uploaded Files</h2>
                        <span className="text-sm text-gray-500">{files.length} file(s)</span>
                    </div>

                    <div className="divide-y divide-gray-100">
                        {files.map((file) => (
                            <div key={file.name} className="p-4 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
                                        <FileSpreadsheet className="w-5 h-5 text-[var(--bridge-blue)]" />
                                    </div>
                                    <div>
                                        <p className="font-medium text-gray-900">{file.name}</p>
                                        <p className="text-sm text-gray-500">
                                            {formatSize(file.size)} • {file.type}
                                            {file.records && ` • ${file.records.toLocaleString()} records`}
                                        </p>
                                    </div>
                                </div>

                                <div className="flex items-center gap-4">
                                    {file.status === "validating" && (
                                        <span className="badge badge-warning flex items-center gap-1">
                                            <Clock className="w-3 h-3 animate-spin" />
                                            Validating
                                        </span>
                                    )}
                                    {file.status === "ready" && (
                                        <span className="badge badge-success flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3" />
                                            Ready
                                        </span>
                                    )}
                                    {file.status === "error" && (
                                        <span className="badge badge-error flex items-center gap-1">
                                            <AlertCircle className="w-3 h-3" />
                                            Error
                                        </span>
                                    )}

                                    <button
                                        onClick={() => removeFile(file.name)}
                                        className="p-1.5 hover:bg-gray-100 rounded"
                                    >
                                        <X className="w-4 h-4 text-gray-400" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>

                    {readyFiles.length > 0 && (
                        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between bg-gray-50">
                            <p className="text-sm text-gray-600">
                                {readyFiles.length} file(s) ready for migration
                            </p>
                            <button
                                onClick={handleStartMigration}
                                disabled={isProcessing}
                                className="btn-primary flex items-center gap-2"
                            >
                                {isProcessing ? (
                                    <>
                                        <Clock className="w-4 h-4 animate-spin" />
                                        Processing...
                                    </>
                                ) : (
                                    <>
                                        Start Migration <ArrowRight className="w-4 h-4" />
                                    </>
                                )}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Supported Formats */}
            <div className="card-forensic">
                <div className="px-6 py-4 border-b border-gray-100">
                    <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                        <HardDrive className="w-5 h-5" />
                        Supported File Formats
                    </h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-6">
                    {supportedFormats.map((format) => (
                        <div key={format.ext} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                            <div className="w-10 h-10 bg-white rounded border border-gray-200 flex items-center justify-center flex-shrink-0">
                                <span className="text-xs font-mono font-bold text-gray-600">{format.ext}</span>
                            </div>
                            <div>
                                <p className="font-medium text-gray-900 text-sm">{format.name}</p>
                                <p className="text-xs text-gray-500">{format.description}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Security Info */}
            <div className="card-forensic p-6 bg-green-50 border-green-200">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Shield className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-green-900">Secure Upload</h3>
                        <p className="text-sm text-green-700 mt-1">
                            All files are encrypted with AES-256-GCM before upload.
                            Data is processed in Canadian data centers only (ca-central-1).
                            Files are automatically deleted after 24 hours.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
