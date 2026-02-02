"""
TeamInvite model - tracks team member invitations and team membership.
"""

from datetime import datetime, timedelta, timezone
from models.database import db
import secrets


class TeamInvite(db.Model):
    """Represents a team member invitation"""
    __tablename__ = 'team_invites'

    # MED-10 FIX: Add index for cleanup queries
    __table_args__ = (
        db.Index('idx_team_invite_status_expires', 'status', 'expires_at'),
        db.Index('idx_team_invite_owner_status', 'owner_user_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Invite details
    email = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='member')  # member, admin
    invite_token = db.Column(db.String(64), unique=True)
    
    # Status tracking
    status = db.Column(db.String(50), default='pending')  # pending, accepted, expired, cancelled
    
    # When accepted, this links to the user who accepted
    accepted_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    accepted_at = db.Column(db.DateTime)
    
    # Relationships
    owner = db.relationship('User', foreign_keys=[owner_user_id], backref='sent_invites')
    accepted_user = db.relationship('User', foreign_keys=[accepted_user_id], backref='received_invites')
    
    @classmethod
    def create_invite(cls, owner_user_id, email, role='member', expiry_days=7, auto_commit=True):
        """
        Create a new team invite.

        FIX HIGH-06: Added auto_commit parameter to allow caller to manage transaction.

        Args:
            owner_user_id: ID of the user creating the invite
            email: Email address to invite
            role: Role for the invited user (member, admin)
            expiry_days: Days until the invite expires
            auto_commit: If True, commits immediately. If False, caller manages transaction.
        """
        invite = cls(
            owner_user_id=owner_user_id,
            email=email.lower().strip(),
            role=role,
            invite_token=secrets.token_urlsafe(32),
            status='pending',
            expires_at=datetime.now(timezone.utc) + timedelta(days=expiry_days)
        )
        db.session.add(invite)

        if auto_commit:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise

        return invite
    
    @classmethod
    def get_pending_for_owner(cls, owner_user_id):
        """Get all pending invites sent by an owner"""
        return cls.query.filter_by(
            owner_user_id=owner_user_id,
            status='pending'
        ).filter(cls.expires_at > datetime.now(timezone.utc)).all()
    
    @classmethod
    def get_team_members(cls, owner_user_id):
        """Get all accepted team members for an owner"""
        from models.user import User
        
        # Get accepted invites
        accepted_invites = cls.query.filter_by(
            owner_user_id=owner_user_id,
            status='accepted'
        ).all()
        
        members = []
        for invite in accepted_invites:
            if invite.accepted_user:
                members.append({
                    'id': invite.accepted_user.id,
                    'email': invite.accepted_user.email,
                    'name': f"{invite.accepted_user.first_name or ''} {invite.accepted_user.last_name or ''}".strip() or invite.accepted_user.email.split('@')[0],
                    'role': invite.role,
                    'joined_at': invite.accepted_at.isoformat() if invite.accepted_at else None
                })
        
        return members
    
    @classmethod
    def find_by_token(cls, token):
        """Find an invite by its token"""
        return cls.query.filter_by(invite_token=token).first()
    
    def accept(self, user_id):
        """Accept this invite"""
        if self.status != 'pending':
            return False, "Invite is no longer valid"
        
        if datetime.now(timezone.utc) > self.expires_at:
            self.status = 'expired'
            db.session.commit()
            return False, "Invite has expired"
        
        self.status = 'accepted'
        self.accepted_user_id = user_id
        self.accepted_at = datetime.now(timezone.utc)
        db.session.commit()
        return True, "Invite accepted"
    
    def cancel(self):
        """Cancel this invite"""
        self.status = 'cancelled'
        db.session.commit()
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'email': self.email,
            'role': self.role,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

    @classmethod
    def cleanup_expired(cls):
        """
        MED-10 FIX: Cleanup expired invites.
        Call this periodically (e.g., from a scheduled job).

        Returns:
            int: Number of invites marked as expired
        """
        now = datetime.now(timezone.utc)
        expired_count = cls.query.filter(
            cls.status == 'pending',
            cls.expires_at < now
        ).update({'status': 'expired'}, synchronize_session=False)
        db.session.commit()
        return expired_count
