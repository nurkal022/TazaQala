from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user, login_user
from functools import wraps
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from app import db
from app.models import Report, User, Notification
from datetime import datetime
import os
import uuid

bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Декоратор для проверки прав администратора или модератора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('admin.login', next=request.url))
        if current_user.role not in ['admin', 'moderator']:
            flash('У вас нет доступа к этой странице', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_only_required(f):
    """Декоратор для проверки прав ТОЛЬКО администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('admin.login', next=request.url))
        if current_user.role != 'admin':
            flash('Эта страница доступна только администратору', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_common_context():
    """Общий контекст для всех страниц админки"""
    return {
        'pending_count': Report.query.filter_by(status='pending').count(),
        'in_progress_count': Report.query.filter_by(status='in_progress').count(),
        'pending_verification_count': Report.query.filter_by(status='pending_verification').count(),
        'notification_count': Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    }


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в админ-панель"""
    if current_user.is_authenticated and current_user.role in ['admin', 'moderator']:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        if not username or not password:
            flash('Заполните все поля', 'danger')
            return render_template('admin/login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user is None:
            flash('Неверное имя пользователя или пароль', 'danger')
            return render_template('admin/login.html')
        
        if not user.check_password(password):
            flash('Неверное имя пользователя или пароль', 'danger')
            return render_template('admin/login.html')
        
        if user.role not in ['admin', 'moderator']:
            flash('У вас нет прав доступа к админ-панели', 'danger')
            return render_template('admin/login.html')
        
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=remember)
        
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('admin.dashboard')
        
        flash(f'Добро пожаловать, {user.username}!', 'success')
        return redirect(next_page)
    
    return render_template('admin/login.html')


@bp.route('/')
@login_required
@admin_required
def dashboard():
    """Дашборд — главная страница админки"""
    ctx = get_common_context()
    
    # Новые репорты (ожидают модерации)
    pending_reports = Report.query.filter_by(status='pending')\
        .order_by(Report.created_at.desc())\
        .limit(20)\
        .all()
    
    # Репорты в работе (для модератора)
    in_progress_reports = Report.query.filter_by(status='in_progress')\
        .order_by(Report.created_at.desc())\
        .limit(20)\
        .all()
    
    # Репорты на финальной проверке (только для админа)
    pending_verification_reports = []
    if current_user.role == 'admin':
        pending_verification_reports = Report.query.filter_by(status='pending_verification')\
            .order_by(Report.cleaned_at.desc())\
            .all()
    
    # Статистика
    stats = {
        'pending': ctx['pending_count'],
        'in_progress': ctx['in_progress_count'],
        'pending_verification': ctx['pending_verification_count'],
        'total_reports': Report.query.count(),
        'total_users': User.query.count(),
        'confirmed': Report.query.filter_by(status='confirmed').count(),
        'cleaned': Report.query.filter_by(status='cleaned').count(),
        'rejected': Report.query.filter_by(status='rejected').count(),
    }
    
    return render_template('admin/dashboard.html',
                         pending_reports=pending_reports,
                         in_progress_reports=in_progress_reports,
                         pending_verification_reports=pending_verification_reports,
                         stats=stats,
                         **ctx)


@bp.route('/reports')
@login_required
@admin_required
def reports():
    """Все репорты"""
    ctx = get_common_context()
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status')
    
    query = Report.query
    
    if status:
        query = query.filter_by(status=status)
    
    reports = query.order_by(Report.created_at.desc())\
        .paginate(page=page, per_page=current_app.config['REPORTS_PER_PAGE'], error_out=False)
    
    return render_template('admin/reports.html', 
                         reports=reports,
                         **ctx)


@bp.route('/report/<int:report_id>/moderate', methods=['POST'])
@login_required
@admin_required
def moderate_report(report_id):
    """Модерация репорта: отклонить или взять в работу"""
    report = Report.query.get_or_404(report_id)
    
    action = request.form.get('action')  # take_work, reject
    comment = request.form.get('comment', '')
    
    if action == 'take_work':
        # Взять в работу → статус in_progress
        report.status = 'in_progress'
        report.moderator_id = current_user.id
        report.moderation_comment = comment
        report.moderated_at = datetime.utcnow()
        
        flash(f'Репорт #{report.id} взят в работу', 'success')
    
    elif action == 'reject':
        report.status = 'rejected'
        report.moderator_id = current_user.id
        report.moderation_comment = comment
        report.moderated_at = datetime.utcnow()
        
        # Уведомление автору
        if report.author:
            report.author.rejected_reports += 1
            
            notification = Notification(
                user_id=report.author.id,
                message=f'Ваш репорт #{report.id} отклонен. {comment}',
                notification_type='report_rejected',
                related_report_id=report.id
            )
            db.session.add(notification)
        
        flash('Репорт отклонен', 'info')
    else:
        flash('Неизвестное действие', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    db.session.commit()
    
    return redirect(url_for('admin.dashboard'))


@bp.route('/report/<int:report_id>/complete', methods=['GET', 'POST'])
@login_required
@admin_required
def complete_cleanup(report_id):
    """Страница завершения уборки модератором"""
    report = Report.query.get_or_404(report_id)
    ctx = get_common_context()
    
    if report.status != 'in_progress':
        flash('Этот репорт не в статусе "В работе"', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        after_photo = request.files.get('after_photo')
        doc_photo = request.files.get('doc_photo')
        
        if not after_photo or not doc_photo:
            flash('Необходимо загрузить фото ПОСЛЕ и документ', 'danger')
            return redirect(url_for('admin.complete_cleanup', report_id=report_id))
        
        # Создаем директорию
        cleanup_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'cleanup')
        os.makedirs(cleanup_dir, exist_ok=True)
        
        # Сохраняем фото ПОСЛЕ
        after_filename = f"after_{uuid.uuid4().hex}_{secure_filename(after_photo.filename)}"
        after_path = os.path.join(cleanup_dir, after_filename)
        after_photo.save(after_path)
        
        # Сохраняем документ
        doc_filename = f"doc_{uuid.uuid4().hex}_{secure_filename(doc_photo.filename)}"
        doc_path = os.path.join(cleanup_dir, doc_filename)
        doc_photo.save(doc_path)
        
        # Обновляем репорт
        report.status = 'pending_verification'
        report.cleaned_at = datetime.utcnow()
        report.cleaned_by_id = current_user.id
        report.cleaned_photo_path = f"cleanup/{after_filename}"
        report.disposal_document_path = f"cleanup/{doc_filename}"
        
        # Уведомление админам
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                message=f'Репорт #{report.id} ожидает финальной проверки от {current_user.username}',
                notification_type='cleanup_verification',
                related_report_id=report.id
            )
            db.session.add(notification)
        
        db.session.commit()
        
        flash('Уборка отправлена на финальную проверку администратору!', 'success')
        return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/complete_cleanup.html', report=report, **ctx)


@bp.route('/final-verification')
@login_required
@admin_only_required
def final_verification():
    """Страница финальной проверки (только для админа)"""
    ctx = get_common_context()
    
    reports = Report.query.filter_by(status='pending_verification')\
        .order_by(Report.cleaned_at.desc())\
        .all()
    
    return render_template('admin/final_verification.html', reports=reports, **ctx)


@bp.route('/verify-cleanup/<int:report_id>')
@login_required
@admin_only_required
def verify_cleanup(report_id):
    """Страница проверки конкретной уборки"""
    report = Report.query.get_or_404(report_id)
    ctx = get_common_context()
    
    if report.status != 'pending_verification':
        flash('Этот репорт не требует проверки', 'warning')
        return redirect(url_for('admin.final_verification'))
    
    # Получаем модератора, который выполнил уборку
    cleaner = User.query.get(report.cleaned_by_id) if report.cleaned_by_id else None
    
    return render_template('admin/verify_cleanup.html', report=report, cleaner=cleaner, **ctx)


@bp.route('/verify-cleanup/<int:report_id>/approve', methods=['POST'])
@login_required
@admin_only_required
def approve_cleanup(report_id):
    """Подтвердить уборку (финальная проверка)"""
    report = Report.query.get_or_404(report_id)
    
    if report.status != 'pending_verification':
        flash('Этот репорт не требует проверки', 'warning')
        return redirect(url_for('admin.final_verification'))
    
    # Финальный статус
    report.status = 'cleaned'
    report.moderator_id = current_user.id
    report.moderated_at = datetime.utcnow()
    
    # Начисляем баллы модератору/клинеру
    if report.cleaned_by_id:
        cleaner = User.query.get(report.cleaned_by_id)
        if cleaner:
            cleaner.add_points(current_app.config.get('POINTS_CLEANED_REPORT', 20))
            
            notification = Notification(
                user_id=cleaner.id,
                message=f'Уборка репорта #{report.id} подтверждена администратором! +{current_app.config.get("POINTS_CLEANED_REPORT", 20)} баллов.',
                notification_type='cleanup_approved',
                related_report_id=report.id
            )
            db.session.add(notification)
    
    # Бонус автору репорта
    if report.author:
        bonus_points = 10
        report.author.add_points(bonus_points)
        
        notification = Notification(
            user_id=report.author.id,
            message=f'Ваш репорт #{report.id} очищен! +{bonus_points} бонусных баллов.',
            notification_type='report_cleaned',
            related_report_id=report.id
        )
        db.session.add(notification)
    
    db.session.commit()
    
    flash('Уборка подтверждена! Баллы начислены.', 'success')
    return redirect(url_for('admin.final_verification'))


@bp.route('/verify-cleanup/<int:report_id>/reject', methods=['POST'])
@login_required
@admin_only_required
def reject_cleanup(report_id):
    """Отклонить уборку — вернуть в работу"""
    report = Report.query.get_or_404(report_id)
    
    if report.status != 'pending_verification':
        flash('Этот репорт не требует проверки', 'warning')
        return redirect(url_for('admin.final_verification'))
    
    comment = request.form.get('comment', 'Уборка не соответствует требованиям')
    
    # Возвращаем в работу
    report.status = 'in_progress'
    report.moderation_comment = comment
    report.moderated_at = datetime.utcnow()
    
    # Уведомление модератору
    if report.cleaned_by_id:
        notification = Notification(
            user_id=report.cleaned_by_id,
            message=f'Уборка репорта #{report.id} отклонена: {comment}. Требуется переделка.',
            notification_type='cleanup_rejected',
            related_report_id=report.id
        )
        db.session.add(notification)
    
    db.session.commit()
    
    flash('Уборка отклонена. Репорт возвращен модератору.', 'info')
    return redirect(url_for('admin.final_verification'))


@bp.route('/users')
@login_required
@admin_only_required
def users():
    """Управление пользователями (только для админа)"""
    ctx = get_common_context()
    page = request.args.get('page', 1, type=int)
    
    users = User.query.order_by(User.total_points.desc())\
        .paginate(page=page, per_page=50, error_out=False)
    
    return render_template('admin/users.html', users=users, **ctx)


@bp.route('/user/<int:user_id>/change_role', methods=['POST'])
@login_required
@admin_only_required
def change_user_role(user_id):
    """Изменить роль пользователя"""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    if new_role in ['user', 'moderator', 'admin']:
        user.role = new_role
        db.session.commit()
        flash(f'Роль пользователя {user.username} изменена на {new_role}', 'success')
    
    return redirect(url_for('admin.users'))


@bp.route('/rewards')
@login_required
@admin_only_required
def rewards():
    """Управление призами (только для админа)"""
    from app.models import Reward
    ctx = get_common_context()
    
    rewards = Reward.query.order_by(Reward.created_at.desc()).all()
    
    return render_template('admin/rewards.html', rewards=rewards, **ctx)


@bp.route('/statistics')
@login_required
@admin_only_required
def statistics():
    """Статистика (только для админа)"""
    from sqlalchemy import func, case
    from datetime import timedelta
    ctx = get_common_context()
    
    stats = {
        'total_reports': Report.query.count(),
        'cleaned': Report.query.filter_by(status='cleaned').count(),
        'in_progress': Report.query.filter_by(status='in_progress').count(),
        'pending': Report.query.filter_by(status='pending').count(),
        'rejected': Report.query.filter_by(status='rejected').count()
    }
    
    # Статистика по дням
    daily_stats = {'labels': [], 'values': []}
    for i in range(29, -1, -1):
        day_start = datetime.utcnow() - timedelta(days=i+1)
        day_end = datetime.utcnow() - timedelta(days=i)
        count = Report.query.filter(
            Report.created_at >= day_start,
            Report.created_at < day_end
        ).count()
        daily_stats['labels'].append(day_start.strftime('%d.%m'))
        daily_stats['values'].append(count)
    
    # По районам
    district_stats_list = Report.query.with_entities(
        Report.district,
        func.count(Report.id).label('total'),
        func.sum(case((Report.status == 'cleaned', 1), else_=0)).label('cleaned')
    ).group_by(Report.district).all()
    
    district_chart_data = {
        'labels': [d.district or 'Не указан' for d in district_stats_list[:10]],
        'totals': [d.total for d in district_stats_list[:10]],
        'cleaned': [d.cleaned or 0 for d in district_stats_list[:10]]
    }
    
    # По категориям
    category_stats_list = Report.query.with_entities(
        func.coalesce(Report.report_category, Report.trash_type, 'trash').label('category'),
        func.count(Report.id).label('count')
    ).group_by('category').all()
    
    label_map = {
        'trash': '🗑️ Мусор',
        'vandalism': '🎨 Вандализм',
        'nature_damage': '🌳 Повреждение природы',
        'illegal_dumping': '🚛 Незаконный сброс',
        'construction_waste': '🏗️ Строительный мусор',
        'hazardous_waste': '⚠️ Опасные отходы',
        'other': '📋 Другое',
        'plastic': 'Пластик',
        'metal': 'Металл/Стекло',
        'organic': 'Органика',
        'mixed': 'Смешанный',
        'construction': 'Строительный',
        'paper': 'Бумага'
    }
    
    trash_type_chart_data = {
        'labels': [label_map.get(t.category, t.category or 'Не указан') for t in category_stats_list],
        'values': [t.count for t in category_stats_list]
    }
    
    return render_template('admin/statistics.html',
                         stats=stats,
                         daily_stats=daily_stats,
                         district_stats=district_stats_list,
                         district_chart_data=district_chart_data,
                         trash_type_chart_data=trash_type_chart_data,
                         **ctx)


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_only_required
def settings():
    """Настройки (только для админа)"""
    ctx = get_common_context()
    
    stats = {
        'total_reports': Report.query.count(),
        'total_users': User.query.count(),
        'pending': Report.query.filter_by(status='pending').count()
    }
    
    if request.method == 'POST':
        flash('Настройки обновлены', 'success')
        return redirect(url_for('admin.settings'))
    
    return render_template('admin/settings.html',
                         config=current_app.config,
                         stats=stats,
                         **ctx)
