import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'taza_qala.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload settings
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # AI Moderation thresholds
    AI_CONFIDENCE_AUTO_APPROVE = 0.85
    AI_AUTO_CONFIRM_THRESHOLD = 0.85  # alias for templates/settings
    AI_CONFIDENCE_REJECT = 0.50
    AI_REJECT_THRESHOLD = 0.50  # alias for templates/settings
    
    # Points system
    POINTS_CONFIRMED_REPORT = 10
    POINTS_WITH_GPS_COMMENT = 5
    POINTS_REPEAT_REPORT = 3
    POINTS_CLEANED_REPORT = 20
    POINTS_FAKE_PENALTY = -10
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Pagination
    REPORTS_PER_PAGE = 20
    LEADERBOARD_TOP = 10
