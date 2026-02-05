from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(255))
    
    # Profile
    full_name = db.Column(db.String(150))
    is_anonymous_display = db.Column(db.Boolean, default=False)
    
    # Role: 'user', 'moderator', 'admin'
    role = db.Column(db.String(20), default='user')
    is_cleaner = db.Column(db.Boolean, default=False)
    
    # Points and level
    total_points = db.Column(db.Integer, default=0)
    points_balance = db.Column(db.Integer, default=0)
    points_spent = db.Column(db.Integer, default=0)
    level = db.Column(db.String(50), default='Новичок')
    
    # Stats
    reports_count = db.Column(db.Integer, default=0)
    confirmed_reports = db.Column(db.Integer, default=0)
    rejected_reports = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    reports = db.relationship('Report', backref='author', lazy='dynamic', foreign_keys='Report.user_id')
    redemptions = db.relationship('RewardRedemption', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def add_points(self, points):
        self.total_points = max(self.total_points + points, 0)
        self.points_balance = max(self.points_balance + points, 0)
        self._update_level()
        db.session.commit()

    def spend_points(self, points):
        if points > self.points_balance:
            raise ValueError('Недостаточно баллов')
        self.points_balance -= points
        self.points_spent += points
        self._update_level()
        db.session.commit()
    
    def _update_level(self):
        if self.total_points >= 500:
            self.level = 'Городской герой'
        elif self.total_points >= 200:
            self.level = 'Эко-патриот'
        elif self.total_points >= 50:
            self.level = 'Активист'
        else:
            self.level = 'Новичок'
    
    def __repr__(self):
        return f'<User {self.username}>'


class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # User info (nullable for anonymous reports)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_anonymous = db.Column(db.Boolean, default=False)
    
    # Location
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(255))
    district = db.Column(db.String(100))
    
    # Content
    photo_path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    trash_type = db.Column(db.String(50))  # Deprecated: kept for backward compatibility
    report_category = db.Column(db.String(50))  # trash, vandalism, nature_damage, illegal_dumping, etc.
    
    # AI Moderation
    ai_confidence = db.Column(db.Float)
    ai_status = db.Column(db.String(20))  # auto_confirmed, needs_review, rejected
    ai_analysis = db.Column(db.Text)  # JSON with AI analysis details
    
    # Status: pending, confirmed, rejected, cleaned
    status = db.Column(db.String(20), default='pending', index=True)
    
    # Moderation
    moderator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    moderation_comment = db.Column(db.Text)
    moderated_at = db.Column(db.DateTime)
    
    # Cleaning verification
    cleaned_at = db.Column(db.DateTime)
    cleaned_photo_path = db.Column(db.String(255))
    cleaned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    disposal_document_path = db.Column(db.String(255), nullable=True)
    
    # Stats
    views_count = db.Column(db.Integer, default=0)
    upvotes = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)  # Soft delete
    
    def __repr__(self):
        return f'<Report {self.id} - {self.status}>'
    
    def is_deleted(self):
        """Проверка, удален ли репорт"""
        return self.deleted_at is not None
    
    def soft_delete(self):
        """Мягкое удаление репорта (сохраняет ID)"""
        self.deleted_at = datetime.utcnow()
        self.status = 'deleted'


class Badge(db.Model):
    __tablename__ = 'badges'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_type = db.Column(db.String(50), nullable=False)  # plastic_hero, metal_warrior, etc.
    badge_name = db.Column(db.String(100), nullable=False)
    badge_icon = db.Column(db.String(100))
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='badges')
    
    def __repr__(self):
        return f'<Badge {self.badge_name}>'


class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50))  # report_confirmed, level_up, etc.
    is_read = db.Column(db.Boolean, default=False)
    related_report_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')
    
    def __repr__(self):
        return f'<Notification {self.id}>'


class Reward(db.Model):
    __tablename__ = 'rewards'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    cost_points = db.Column(db.Integer, nullable=False)
    image_path = db.Column(db.String(255))
    category = db.Column(db.String(80))
    total_quantity = db.Column(db.Integer, nullable=True)  # None = unlimited
    redeemed_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_digital = db.Column(db.Boolean, default=False)
    delivery_info = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    redemptions = db.relationship('RewardRedemption', backref='reward', lazy='dynamic')

    @property
    def available_quantity(self):
        if self.total_quantity is None:
            return None
        return max(self.total_quantity - self.redeemed_count, 0)

    def is_available(self):
        if not self.is_active:
            return False
        if self.total_quantity is None:
            return True
        return self.redeemed_count < self.total_quantity

    def __repr__(self):
        return f'<Reward {self.title}>'


class RewardRedemption(db.Model):
    __tablename__ = 'reward_redemptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reward_id = db.Column(db.Integer, db.ForeignKey('rewards.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, delivered, cancelled
    comment = db.Column(db.String(255))
    points_spent = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<RewardRedemption {self.id} - {self.status}>'

