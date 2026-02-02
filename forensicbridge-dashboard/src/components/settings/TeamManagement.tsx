'use client';

import { useState, useEffect } from 'react';
import { Users, Mail, UserPlus, Crown, User, X, Loader2 } from 'lucide-react';
import { authFetch } from '@/lib/auth';

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface TeamMember {
    id: number;
    email: string;
    name: string;
    role: string;
    joined_at: string | null;
}

interface PendingInvite {
    email: string;
    role: string;
    status: string;
}

export function TeamManagement() {
    const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
    const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
    const [loading, setLoading] = useState(true);
    const [showInviteModal, setShowInviteModal] = useState(false);
    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteRole, setInviteRole] = useState('member');
    const [inviting, setInviting] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    useEffect(() => {
        loadTeamData();
    }, []);

    const loadTeamData = async () => {
        try {
            // SECURITY FIX: Use authFetch for proper CSRF token and httpOnly cookie handling
            const response = await authFetch(`${API_URL}/api/auth/team`);

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    setTeamMembers(data.team_members || []);
                    setPendingInvites(data.pending_invites || []);
                }
            } else if (response.status === 403) {
                setError('Team management requires Enterprise or Forensic tier');
            }
        } catch (err) {
            // FIX: Only log in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error('Failed to load team data:', err);
            }
        } finally {
            setLoading(false);
        }
    };

    const handleInvite = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        setInviting(true);

        try {
            // SECURITY FIX: Use authFetch for proper CSRF token and httpOnly cookie handling
            const response = await authFetch(`${API_URL}/api/auth/team/invite`, {
                method: 'POST',
                body: JSON.stringify({
                    email: inviteEmail,
                    role: inviteRole
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to send invite');
            }

            setSuccess(`Invitation sent to ${inviteEmail}`);
            setInviteEmail('');
            setShowInviteModal(false);
            loadTeamData(); // Refresh list
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send invite');
        } finally {
            setInviting(false);
        }
    };

    if (loading) {
        return (
            <div className="card-forensic p-6 flex items-center justify-center h-48">
                <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
        );
    }

    return (
        <div className="card-forensic p-6">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h2 className="text-lg font-semibold">Team Members</h2>
                    <p className="text-sm text-gray-500">Manage your team's access to ForensicBridge</p>
                </div>
                <button
                    onClick={() => setShowInviteModal(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-[var(--bridge-blue)] text-white rounded-lg hover:bg-[var(--bridge-blue)]/90 transition-colors"
                >
                    <UserPlus className="w-4 h-4" />
                    Invite Member
                </button>
            </div>

            {/* Error/Success Messages */}
            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg">
                    {error}
                </div>
            )}
            {success && (
                <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded-lg">
                    {success}
                </div>
            )}

            {/* Team Members List */}
            <div className="space-y-3" role="list" aria-label="Team members">
                {teamMembers.length === 0 ? (
                    <div className="p-8 text-center text-gray-500" role="status">
                        <Users className="w-12 h-12 mx-auto text-gray-300 mb-3" aria-hidden="true" />
                        <p className="text-lg font-medium text-gray-600">No team members yet</p>
                        <p className="text-sm">Invite team members to collaborate on migrations</p>
                    </div>
                ) : null}
                {teamMembers.map((member) => (
                    <div
                        key={member.id}
                        className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                    >
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-[var(--bridge-blue)]/10 rounded-full flex items-center justify-center">
                                {member.role === 'Owner' ? (
                                    <Crown className="w-5 h-5 text-[var(--forensic-gold)]" />
                                ) : (
                                    <User className="w-5 h-5 text-[var(--bridge-blue)]" />
                                )}
                            </div>
                            <div>
                                <p className="font-medium">{member.name}</p>
                                <p className="text-sm text-gray-500">{member.email}</p>
                            </div>
                        </div>
                        <span className={`px-3 py-1 rounded-full text-xs font-medium ${member.role === 'Owner'
                                ? 'bg-[var(--forensic-gold)]/10 text-[var(--forensic-gold)]'
                                : 'bg-gray-200 text-gray-600'
                            }`}>
                            {member.role}
                        </span>
                    </div>
                ))}
            </div>

            {/* Pending Invites */}
            {pendingInvites.length > 0 && (
                <div className="mt-6">
                    <h3 className="text-sm font-medium text-gray-500 mb-3">Pending Invitations</h3>
                    <div className="space-y-2">
                        {pendingInvites.map((invite, index) => (
                            <div
                                key={index}
                                className="flex items-center justify-between p-3 bg-amber-50 border border-amber-200 rounded-lg"
                            >
                                <div className="flex items-center gap-2">
                                    <Mail className="w-4 h-4 text-amber-600" />
                                    <span className="text-sm">{invite.email}</span>
                                </div>
                                <span className="text-xs text-amber-600">Pending</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Invite Modal */}
            {showInviteModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-full max-w-md mx-4">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-semibold">Invite Team Member</h3>
                            <button
                                onClick={() => setShowInviteModal(false)}
                                className="p-1 hover:bg-gray-100 rounded"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <form onSubmit={handleInvite} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Email Address
                                </label>
                                <input
                                    type="email"
                                    value={inviteEmail}
                                    onChange={(e) => setInviteEmail(e.target.value)}
                                    required
                                    className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                                    placeholder="colleague@company.com"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Role
                                </label>
                                <select
                                    value={inviteRole}
                                    onChange={(e) => setInviteRole(e.target.value)}
                                    className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                                >
                                    <option value="member">Member</option>
                                    <option value="admin">Admin</option>
                                </select>
                            </div>

                            <div className="flex gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowInviteModal(false)}
                                    className="flex-1 px-4 py-2 border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={inviting}
                                    className="flex-1 px-4 py-2 bg-[var(--bridge-blue)] text-white rounded-lg hover:bg-[var(--bridge-blue)]/90 disabled:opacity-50"
                                >
                                    {inviting ? 'Sending...' : 'Send Invite'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
