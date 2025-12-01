
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Report, Notification
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from functools import wraps

bp = Blueprint('cleaner', __name__, url_prefix='/cleaner')

def cleaner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_cleaner and current_user.role != 'admin':
            flash('Доступ запрещен. Требуются права сотрудника очистки.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@bp.route('/')
@cleaner_required
def dashboard():
    """Панель управления клинера"""
    # Репорты, требующие уборки (подтвержденные)
    confirmed_reports = Report.query.filter_by(status='confirmed').order_by(Report.created_at.desc()).all()
    
    # Репорты, убранные текущим клинером
    my_cleaned_reports = Report.query.filter_by(cleaned_by_id=current_user.id).order_by(Report.cleaned_at.desc()).all()
    
    return render_template('cleaner/dashboard.html',
                         confirmed_reports=confirmed_reports,
                         my_cleaned_reports=my_cleaned_reports)

@bp.route('/report/<int:report_id>/complete', methods=['GET', 'POST'])
@cleaner_required
def complete_cleanup(report_id):
    """Завершение уборки"""
    report = Report.query.get_or_404(report_id)
    
    if report.status != 'confirmed':
        flash('Этот репорт нельзя отметить как убранный', 'warning')
        return redirect(url_for('cleaner.dashboard'))
    
    if request.method == 'POST':
        after_photo = request.files.get('after_photo')
        doc_photo = request.files.get('doc_photo')
        
        if not after_photo or not doc_photo:
            flash('Необходимо загрузить оба фото: результат уборки и документ об утилизации', 'danger')
            return redirect(url_for('cleaner.complete_cleanup', report_id=report_id))
            
        if not allowed_file(after_photo.filename) or not allowed_file(doc_photo.filename):
            flash('Недопустимый формат файла', 'danger')
            return redirect(url_for('cleaner.complete_cleanup', report_id=report_id))
            
        # Сохраняем фото
        after_filename = f"after_{uuid.uuid4().hex}_{secure_filename(after_photo.filename)}"
        doc_filename = f"doc_{uuid.uuid4().hex}_{secure_filename(doc_photo.filename)}"
        
        # Создаем директорию если нет
        cleanup_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'cleanup')
        os.makedirs(cleanup_dir, exist_ok=True)
        
        after_path = os.path.join(cleanup_dir, after_filename)
        doc_path = os.path.join(cleanup_dir, doc_filename)
        
        after_photo.save(after_path)
        doc_photo.save(doc_path)
        
        # Пути относительно static/uploads
        rel_after_path = os.path.join('cleanup', after_filename)
        rel_doc_path = os.path.join('cleanup', doc_filename)
        
        # Обновляем репорт
        report.status = 'pending_verification'
        report.cleaned_at = datetime.utcnow()
        report.cleaned_by_id = current_user.id
        report.cleaned_photo_path = rel_after_path
        report.disposal_document_path = rel_doc_path
        
        # Создаем уведомление для администраторов
        from app.models import User
        admins = User.query.filter(User.role.in_(['admin', 'moderator'])).all()
        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                message=f'Требуется проверка уборки репорта #{report.id} от {current_user.full_name or current_user.username}',
                notification_type='cleanup_verification',
                related_report_id=report.id
            )
            db.session.add(notification)
            
        db.session.commit()
        
        flash('Отлично! Уборка отправлена на проверку администратору.', 'success')
        return redirect(url_for('cleaner.dashboard'))
        
    return render_template('cleaner/complete_cleanup.html', report=report)
