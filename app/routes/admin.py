from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user, login_user
from functools import wraps
from urllib.parse import urlparse
from app import db
from app.models import Report, User, Notification
from datetime import datetime

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему администратора', 'warning')
            return redirect(url_for('admin.login', next=request.url))
        if current_user.role not in ['admin', 'moderator']:
            flash('У вас нет доступа к этой странице', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в админ-панель"""
    if current_user.is_authenticated and current_user.role in ['admin', 'moderator']:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Неверное имя пользователя или пароль', 'danger')
            return render_template('admin/login.html')
        
        # Проверяем права администратора
        if user.role not in ['admin', 'moderator']:
            flash('У вас нет прав доступа к админ-панели', 'danger')
            return render_template('admin/login.html')
        
        # Обновляем время последнего входа
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=remember)
        
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('admin.dashboard')
        
        flash(f'Добро пожаловать в админ-панель, {user.username}!', 'success')
        return redirect(next_page)
    
    return render_template('admin/login.html')

@bp.route('/')
@login_required
@admin_required
def dashboard():
    """Админ-панель - главная"""
    from sqlalchemy import func
    
    # Репорты, ожидающие модерации
    pending_reports = Report.query.filter_by(ai_status='needs_review')\
        .order_by(Report.created_at.desc())\
        .limit(20)\
        .all()
    
    # Репорты, ожидающие проверки уборки
    pending_verification_reports = Report.query.filter_by(status='pending_verification')\
        .order_by(Report.cleaned_at.desc())\
        .all()
    
    # Статистика
    stats = {
        'pending_moderation': Report.query.filter_by(ai_status='needs_review').count(),
        'pending_verification': Report.query.filter_by(status='pending_verification').count(),
        'total_reports': Report.query.count(),
        'total_users': User.query.count(),
        'ai_auto_confirmed': Report.query.filter_by(ai_status='auto_confirmed').count(),
        'confirmed': Report.query.filter_by(status='confirmed').count(),
        'cleaned': Report.query.filter_by(status='cleaned').count(),
        'rejected': Report.query.filter_by(status='rejected').count(),
        'pending_count': Report.query.filter_by(ai_status='needs_review').count()
    }
    
    # Для боковой панели
    pending_count = stats['pending_moderation']
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    return render_template('admin/dashboard.html', 
                         reports=pending_reports,
                         pending_verification_reports=pending_verification_reports,
                         stats=stats,
                         pending_count=pending_count,
                         notification_count=notification_count)

@bp.route('/reports')
@login_required
@admin_required
def reports():
    """Все репорты"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status')
    
    query = Report.query
    
    if status:
        query = query.filter_by(status=status)
    
    reports = query.order_by(Report.created_at.desc())\
        .paginate(page=page, per_page=current_app.config['REPORTS_PER_PAGE'], error_out=False)
    
    pending_count = Report.query.filter_by(ai_status='needs_review').count()
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    return render_template('admin/reports.html', 
                         reports=reports,
                         pending_count=pending_count,
                         notification_count=notification_count)

@bp.route('/report/<int:report_id>/moderate', methods=['POST'])
@login_required
@admin_required
def moderate_report(report_id):
    """Модерация репорта"""
    report = Report.query.get_or_404(report_id)
    
    action = request.form.get('action')  # approve, reject
    comment = request.form.get('comment', '')
    
    if action == 'approve':
        report.status = 'confirmed'
        report.ai_status = 'auto_confirmed'  # Обновляем AI статус, чтобы репорт исчез из списка "на проверке"
        report.moderator_id = current_user.id
        report.moderation_comment = comment
        report.moderated_at = datetime.utcnow()
        
        # Начисляем баллы автору
        if report.author:
            points = current_app.config['POINTS_CONFIRMED_REPORT']
            if report.description:
                points += current_app.config['POINTS_WITH_GPS_COMMENT']
            
            report.author.add_points(points)
            report.author.confirmed_reports += 1
            
            # Уведомление
            notification = Notification(
                user_id=report.author.id,
                message=f'Ваш репорт #{report.id} подтвержден модератором! +{points} баллов.',
                notification_type='report_confirmed',
                related_report_id=report.id
            )
            db.session.add(notification)
        
        flash('Репорт подтвержден', 'success')
    
    elif action == 'reject':
        report.status = 'rejected'
        report.ai_status = 'rejected'  # Обновляем AI статус
        report.moderator_id = current_user.id
        report.moderation_comment = comment
        report.moderated_at = datetime.utcnow()
        
        # Штраф за фейк (если есть комментарий "фейк")
        if report.author and 'фейк' in comment.lower():
            report.author.add_points(current_app.config['POINTS_FAKE_PENALTY'])
            report.author.rejected_reports += 1
            
            # Уведомление
            notification = Notification(
                user_id=report.author.id,
                message=f'Ваш репорт #{report.id} отклонен: {comment}',
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

@bp.route('/users')
@login_required
@admin_required
def users():
    """Управление пользователями"""
    page = request.args.get('page', 1, type=int)
    
    users = User.query.order_by(User.total_points.desc())\
        .paginate(page=page, per_page=50, error_out=False)
    
    pending_count = Report.query.filter_by(ai_status='needs_review').count()
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    return render_template('admin/users.html', 
                         users=users,
                         pending_count=pending_count,
                         notification_count=notification_count)

@bp.route('/user/<int:user_id>/change_role', methods=['POST'])
@login_required
@admin_required
def change_user_role(user_id):
    """Изменить роль пользователя"""
    if current_user.role != 'admin':
        flash('Только администратор может изменять роли', 'danger')
        return redirect(url_for('admin.users'))
    
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    if new_role in ['user', 'moderator', 'admin']:
        user.role = new_role
        db.session.commit()
        flash(f'Роль пользователя {user.username} изменена на {new_role}', 'success')
    
    return redirect(url_for('admin.users'))

@bp.route('/rewards')
@login_required
@admin_required
def rewards():
    """Управление призами"""
    from app.models import Reward
    
    rewards = Reward.query.order_by(Reward.created_at.desc()).all()
    pending_count = Report.query.filter_by(ai_status='needs_review').count()
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    return render_template('admin/rewards.html', 
                         rewards=rewards,
                         pending_count=pending_count,
                         notification_count=notification_count)

@bp.route('/statistics')
@login_required
@admin_required
def statistics():
    """Статистика с графиками"""
    from sqlalchemy import func, case
    from datetime import datetime, timedelta
    
    # Основная статистика
    stats = {
        'total_reports': Report.query.count(),
        'cleaned': Report.query.filter_by(status='cleaned').count(),
        'confirmed': Report.query.filter_by(status='confirmed').count(),
        'pending': Report.query.filter_by(status='pending').count(),
        'rejected': Report.query.filter_by(status='rejected').count()
    }
    
    # Статистика по дням (последние 30 дней)
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
    
    # Статистика по районам для графика
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
    
    # Статистика по категориям отчетов для графика
    from sqlalchemy import case
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
        # Старые типы для обратной совместимости
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
    
    pending_count = Report.query.filter_by(ai_status='needs_review').count()
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    return render_template('admin/statistics.html',
                         stats=stats,
                         daily_stats=daily_stats,
                         district_stats=district_stats_list,
                         district_chart_data=district_chart_data,
                         trash_type_chart_data=trash_type_chart_data,
                         pending_count=pending_count,
                         notification_count=notification_count)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """Настройки системы"""
    pending_count = Report.query.filter_by(ai_status='needs_review').count()
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    stats = {
        'total_reports': Report.query.count(),
        'total_users': User.query.count(),
        'pending_moderation': Report.query.filter_by(ai_status='needs_review').count()
    }
    
    if request.method == 'POST':
        # Здесь можно добавить изменение настроек баллов и т.д.
        flash('Настройки обновлены', 'success')
        return redirect(url_for('admin.settings'))
    
    return render_template('admin/settings.html',
                         config=current_app.config,
                         stats=stats,
                         pending_count=pending_count,
                         notification_count=notification_count)


@bp.route('/verify-cleanup/<int:report_id>')
@login_required
@admin_required
def verify_cleanup(report_id):
    """Страница проверки уборки"""
    report = Report.query.get_or_404(report_id)
    
    if report.status != 'pending_verification':
        flash('Этот репорт не требует проверки уборки', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    pending_count = Report.query.filter_by(ai_status='needs_review').count()
    notification_count = Notification.query.filter_by(is_read=False).count() if hasattr(Notification, 'is_read') else 0
    
    return render_template('admin/verify_cleanup.html',
                         report=report,
                         pending_count=pending_count,
                         notification_count=notification_count)


@bp.route('/verify-cleanup/<int:report_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_cleanup(report_id):
    """Подтвердить уборку"""
    report = Report.query.get_or_404(report_id)
    
    if report.status != 'pending_verification':
        flash('Этот репорт не требует проверки уборки', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    # Меняем статус на cleaned
    report.status = 'cleaned'
    report.moderator_id = current_user.id
    report.moderated_at = datetime.utcnow()
    
    # Начисляем баллы клинеру
    if report.cleaned_by_id:
        cleaner = User.query.get(report.cleaned_by_id)
        if cleaner:
            cleaner.add_points(20)
            
            # Уведомление клинеру
            notification = Notification(
                user_id=cleaner.id,
                message=f'Ваша уборка репорта #{report.id} подтверждена! +20 баллов.',
                notification_type='cleanup_approved',
                related_report_id=report.id
            )
            db.session.add(notification)
    
    # Начисляем баллы автору репорта (бонус за уборку)
    if report.author:
        report.author.add_points(current_app.config.get('POINTS_CLEANED_REPORT', 50))
        
        # Уведомление автору
        notification = Notification(
            user_id=report.author.id,
            message=f'Ваш репорт #{report.id} убран! Локация очищена.',
            notification_type='report_cleaned',
            related_report_id=report.id
        )
        db.session.add(notification)
    
    db.session.commit()
    
    flash('Уборка подтверждена! Баллы начислены.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/verify-cleanup/<int:report_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_cleanup(report_id):
    """Отклонить уборку"""
    report = Report.query.get_or_404(report_id)
    
    if report.status != 'pending_verification':
        flash('Этот репорт не требует проверки уборки', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    comment = request.form.get('comment', 'Уборка не соответствует требованиям')
    
    # Возвращаем статус к confirmed
    report.status = 'confirmed'
    report.cleaned_at = None
    report.cleaned_by_id = None
    report.cleaned_photo_path = None
    report.disposal_document_path = None
    report.moderator_id = current_user.id
    report.moderation_comment = comment
    report.moderated_at = datetime.utcnow()
    
    # Уведомление клинеру
    if report.cleaned_by_id:
        cleaner = User.query.get(report.cleaned_by_id)
        if cleaner:
            notification = Notification(
                user_id=cleaner.id,
                message=f'Ваша уборка репорта #{report.id} отклонена: {comment}',
                notification_type='cleanup_rejected',
                related_report_id=report.id
            )
            db.session.add(notification)
    
    db.session.commit()
    
    flash('Уборка отклонена. Репорт возвращен в статус "Подтвержден".', 'info')
    return redirect(url_for('admin.dashboard'))

