'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Building2, Mail, FileText, Loader2, Download } from 'lucide-react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export default function NewProjectPage() {
    const router = useRouter();
    const [name, setName] = useState('');
    const [clientName, setClientName] = useState('');
    const [clientEmail, setClientEmail] = useState('');
    const [notes, setNotes] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [createdProject, setCreatedProject] = useState<{
        id: number;
        session_id: string;
        name: string;
    } | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const token = localStorage.getItem('token');
            if (!token) {
                router.push('/login');
                return;
            }

            const response = await fetch(`${API_URL}/api/projects`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    name,
                    client_name: clientName,
                    client_email: clientEmail,
                    notes,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to create project');
            }

            setCreatedProject(data.project);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create project');
        } finally {
            setLoading(false);
        }
    };

    if (createdProject) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 py-12">
                <div className="max-w-2xl mx-auto px-4">
                    <div className="bg-slate-800/50 backdrop-blur-xl rounded-2xl p-8 shadow-2xl border border-slate-700/50">
                        <div className="text-center mb-8">
                            <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <h2 className="text-2xl font-bold text-white mb-2">Project Created!</h2>
                            <p className="text-slate-400">Your migration project is ready</p>
                        </div>

                        <div className="bg-slate-900/50 rounded-xl p-6 mb-6">
                            <h3 className="text-sm font-medium text-slate-400 mb-2">Session ID</h3>
                            <div className="flex items-center gap-3">
                                <code className="flex-1 text-lg font-mono text-emerald-400 bg-slate-800 px-4 py-3 rounded-lg">
                                    {createdProject.session_id}
                                </code>
                                <button
                                    onClick={() => navigator.clipboard.writeText(createdProject.session_id)}
                                    className="p-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors"
                                >
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                    </svg>
                                </button>
                            </div>
                        </div>

                        <div className="space-y-4 mb-8">
                            <h3 className="text-lg font-semibold text-white">Next Steps</h3>
                            <ol className="space-y-3 text-slate-300">
                                <li className="flex items-start gap-3">
                                    <span className="flex-shrink-0 w-6 h-6 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center text-sm font-medium">1</span>
                                    <span>Download the ForensicBridge extractor tool</span>
                                </li>
                                <li className="flex items-start gap-3">
                                    <span className="flex-shrink-0 w-6 h-6 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center text-sm font-medium">2</span>
                                    <span>Run it on the client&apos;s Windows machine with QuickBooks</span>
                                </li>
                                <li className="flex items-start gap-3">
                                    <span className="flex-shrink-0 w-6 h-6 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center text-sm font-medium">3</span>
                                    <span>Enter the Session ID: <code className="text-emerald-400">{createdProject.session_id}</code></span>
                                </li>
                                <li className="flex items-start gap-3">
                                    <span className="flex-shrink-0 w-6 h-6 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center text-sm font-medium">4</span>
                                    <span>Return here to monitor progress</span>
                                </li>
                            </ol>
                        </div>

                        <div className="flex gap-3">
                            <a
                                href={`${API_URL}/api/extractor/download`}
                                className="flex-1 py-3 px-4 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-500 text-white font-medium hover:from-emerald-600 hover:to-teal-600 flex items-center justify-center gap-2 transition-all"
                            >
                                <Download className="w-5 h-5" />
                                Download Extractor
                            </a>
                            <Link
                                href={`/projects/${createdProject.id}`}
                                className="py-3 px-6 rounded-lg bg-slate-700 text-white font-medium hover:bg-slate-600 transition-colors"
                            >
                                View Project
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 py-12">
            <div className="max-w-2xl mx-auto px-4">
                <Link
                    href="/"
                    className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-6 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Dashboard
                </Link>

                <div className="bg-slate-800/50 backdrop-blur-xl rounded-2xl p-8 shadow-2xl border border-slate-700/50">
                    <h1 className="text-2xl font-bold text-white mb-2">New Migration Project</h1>
                    <p className="text-slate-400 mb-8">Create a project to track your client&apos;s migration</p>

                    {error && (
                        <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div>
                            <label htmlFor="name" className="block text-sm font-medium text-slate-300 mb-2">
                                <FileText className="w-4 h-4 inline mr-2" />
                                Project Name
                            </label>
                            <input
                                id="name"
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="e.g., Q1 2026 Migration"
                            />
                        </div>

                        <div>
                            <label htmlFor="clientName" className="block text-sm font-medium text-slate-300 mb-2">
                                <Building2 className="w-4 h-4 inline mr-2" />
                                Client Company Name
                            </label>
                            <input
                                id="clientName"
                                type="text"
                                value={clientName}
                                onChange={(e) => setClientName(e.target.value)}
                                required
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="e.g., Waterloo Manufacturing"
                            />
                        </div>

                        <div>
                            <label htmlFor="clientEmail" className="block text-sm font-medium text-slate-300 mb-2">
                                <Mail className="w-4 h-4 inline mr-2" />
                                Client Email (Optional)
                            </label>
                            <input
                                id="clientEmail"
                                type="email"
                                value={clientEmail}
                                onChange={(e) => setClientEmail(e.target.value)}
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="client@company.com"
                            />
                        </div>

                        <div>
                            <label htmlFor="notes" className="block text-sm font-medium text-slate-300 mb-2">
                                Notes (Optional)
                            </label>
                            <textarea
                                id="notes"
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                rows={3}
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all resize-none"
                                placeholder="Any special instructions or notes..."
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-3 px-4 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-500 text-white font-medium hover:from-emerald-600 hover:to-teal-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    Creating Project...
                                </>
                            ) : (
                                'Create Project'
                            )}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
