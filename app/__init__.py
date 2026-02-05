import os
from flask import Flask, render_template, request, url_for
from flask_migrate import Migrate
from config import Config
from sqlalchemy import inspect, text
from extensions import db, login_manager

migrate = Migrate()

def create_app(config_class=Config):
    # Указываем правильные пути к static и templates
    # Поддержка подпути для развертывания на /taza_qala
    # SCRIPT_NAME будет передаваться через заголовки от nginx
    app = Flask(
        __name__,
        static_folder='../static',
        static_url_path='/static'
    )
    app.config.from_object(config_class)
    
    # Middleware для обработки подпути /taza_qala из заголовков nginx
    @app.before_request
    def set_script_name():
        # Получаем SCRIPT_NAME из environ (уже установлен WSGI middleware)
        script_name = request.environ.get('SCRIPT_NAME', '')
        if script_name:
            # Устанавливаем APPLICATION_ROOT для правильной генерации URL
            # Flask автоматически использует SCRIPT_NAME из environ
            app.config['APPLICATION_ROOT'] = script_name
            # Также убеждаемся, что request.url_adapter видит script_name
            if hasattr(request, 'url_adapter') and request.url_adapter:
                request.url_adapter.script_name = script_name
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    
    # Create upload folder if not exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from app.routes import main, auth, reports, api, admin
    
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    
    from app.routes import cleaner
    app.register_blueprint(cleaner.bp)
    
    # Create database tables and initial admin
    with app.app_context():
        db.create_all()

        # Apply lightweight schema patch for legacy databases without migrations
        _ensure_points_columns()
        _ensure_report_category_column()
        _ensure_deleted_at_column()
        
        # Create default admin user if not exists
        from app.models import User
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@cleanalmaty.kz',
                role='admin',
                full_name='Администратор'
            )
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print("✅ Создан администратор: логин 'admin', пароль 'admin'")
    
    # Register error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404
    
    # Helper function for report photo URL
    @app.template_filter('report_photo_url')
    def report_photo_url_filter(photo_path):
        """Формирует правильный URL для фото репорта"""
        if not photo_path:
            return url_for('static', filename='image.png')  # Буферное фото по умолчанию
        if photo_path == 'image.png':
            return url_for('static', filename='image.png')  # Буферное фото
        if photo_path.startswith('http'):
            return photo_path  # Внешний URL
        if photo_path.startswith('uploads/'):
            return url_for('static', filename=photo_path)
        return url_for('static', filename='uploads/' + photo_path)
    
    # Helper function for cleaned photo URL
    @app.template_filter('cleaned_photo_url')
    def cleaned_photo_url_filter(photo_path):
        """Формирует правильный URL для фото после уборки"""
        if not photo_path:
            return url_for('static', filename='img_after.jpeg')  # Буферное фото по умолчанию
        if photo_path == 'img_after.jpeg':
            return url_for('static', filename='img_after.jpeg')  # Буферное фото
        if photo_path.startswith('http'):
            return photo_path  # Внешний URL
        if photo_path.startswith('uploads/'):
            return url_for('static', filename=photo_path)
        return url_for('static', filename='uploads/' + photo_path)
    
    return app

def _ensure_points_columns():
    """Добавляет новые колонки баллов, если база была создана раньше"""
    inspector = inspect(db.engine)
    if 'users' not in inspector.get_table_names():
        return
    
    columns = {col['name'] for col in inspector.get_columns('users')}
    altered = False
    
    if 'points_balance' not in columns:
        try:
            db.session.execute(text('ALTER TABLE users ADD COLUMN points_balance INTEGER DEFAULT 0'))
            altered = True
            print("ℹ️ Добавлена колонка users.points_balance")
        except Exception as exc:
            print(f"⚠️ Не удалось добавить points_balance: {exc}")
    
    if 'points_spent' not in columns:
        try:
            db.session.execute(text('ALTER TABLE users ADD COLUMN points_spent INTEGER DEFAULT 0'))
            altered = True
            print("ℹ️ Добавлена колонка users.points_spent")
        except Exception as exc:
            print(f"⚠️ Не удалось добавить points_spent: {exc}")
    
    if altered:
        try:
            db.session.execute(text('UPDATE users SET points_balance = total_points WHERE points_balance IS NULL'))
            db.session.execute(text('UPDATE users SET points_spent = 0 WHERE points_spent IS NULL'))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"⚠️ Не удалось обновить значения баллов: {exc}")

def _ensure_report_category_column():
    """Добавляет колонку report_category, если база была создана раньше"""
    inspector = inspect(db.engine)
    if 'reports' not in inspector.get_table_names():
        return
    
    columns = {col['name'] for col in inspector.get_columns('reports')}
    
    if 'report_category' not in columns:
        try:
            db.session.execute(text('ALTER TABLE reports ADD COLUMN report_category VARCHAR(50)'))
            # Мигрируем старые данные: если есть trash_type, устанавливаем report_category = 'trash'
            db.session.execute(text("UPDATE reports SET report_category = 'trash' WHERE trash_type IS NOT NULL AND report_category IS NULL"))
            db.session.commit()
            print("ℹ️ Добавлена колонка reports.report_category")
        except Exception as exc:
            db.session.rollback()
            print(f"⚠️ Не удалось добавить report_category: {exc}")

def _ensure_deleted_at_column():
    """Добавляет колонку deleted_at для soft delete, если база была создана раньше"""
    inspector = inspect(db.engine)
    if 'reports' not in inspector.get_table_names():
        return
    
    columns = {col['name'] for col in inspector.get_columns('reports')}
    
    if 'deleted_at' not in columns:
        try:
            db.session.execute(text('ALTER TABLE reports ADD COLUMN deleted_at DATETIME'))
            db.session.commit()
            print("ℹ️ Добавлена колонка reports.deleted_at")
        except Exception as exc:
            db.session.rollback()
            print(f"⚠️ Не удалось добавить deleted_at: {exc}")

from app import models

