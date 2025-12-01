import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Report, Notification
from app.ai_moderator_openai import openai_moderator
from datetime import datetime
import uuid

bp = Blueprint('reports', __name__, url_prefix='/reports')

def allowed_file(filename):
    """Проверка разрешенного расширения файла"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@bp.route('/new', methods=['GET', 'POST'])
def new_report():
    """Создание нового репорта"""
    if request.method == 'POST':
        # Получаем данные из формы
        latitude = request.form.get('latitude', type=float)
        longitude = request.form.get('longitude', type=float)
        description = request.form.get('description', '')
        address = request.form.get('address', '')
        district = request.form.get('district', '')
        report_category = request.form.get('report_category', 'trash')
        
        # Проверка файла
        if 'photo' not in request.files:
            flash('Необходимо прикрепить фотографию', 'danger')
            return render_template('reports/new.html')
        
        file = request.files['photo']
        
        if file.filename == '':
            flash('Файл не выбран', 'danger')
            return render_template('reports/new.html')
        
        if not allowed_file(file.filename):
            flash('Недопустимый формат файла. Разрешены: png, jpg, jpeg, gif, webp', 'danger')
            return render_template('reports/new.html')
        
        # Валидация координат
        if not latitude or not longitude:
            flash('Необходимо указать местоположение на карте', 'danger')
            return render_template('reports/new.html')
        
        # Сохраняем файл
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        # AI-модерация через OpenAI Vision API
        ai_result = openai_moderator.analyze_image(filepath)
        
        # Создаем репорт
        report = Report(
            user_id=current_user.id if current_user.is_authenticated else None,
            is_anonymous=not current_user.is_authenticated,
            latitude=latitude,
            longitude=longitude,
            address=address,
            district=district,
            description=description,
            photo_path=unique_filename,
            report_category=report_category,
            ai_confidence=ai_result['confidence'],
            ai_status=ai_result['status'],
            ai_analysis=ai_result['analysis'],
            trash_type=ai_result.get('trash_type'),  # Для обратной совместимости
            status='pending' if ai_result['status'] != 'auto_confirmed' else 'confirmed'
        )
        
        db.session.add(report)
        
        # Начисляем баллы зарегистрированному пользователю
        if current_user.is_authenticated:
            points = current_app.config['POINTS_CONFIRMED_REPORT']
            
            # Дополнительные баллы за GPS и комментарий
            if description:
                points += current_app.config['POINTS_WITH_GPS_COMMENT']
            
            current_user.add_points(points)
            current_user.reports_count += 1
            
            if report.status == 'confirmed':
                current_user.confirmed_reports += 1
            
            # Создаем уведомление
            notification = Notification(
                user_id=current_user.id,
                message=f'Ваш репорт получен! Статус: {report.status}. Начислено {points} баллов.',
                notification_type='report_submitted',
                related_report_id=report.id
            )
            db.session.add(notification)
        
        db.session.commit()
        
        # Сообщение пользователю
        if report.status == 'confirmed':
            flash(f'Спасибо! Ваш репорт подтвержден AI-модерацией (достоверность: {ai_result["confidence"]*100:.0f}%)', 'success')
        else:
            flash('Спасибо! Ваш репорт отправлен на проверку модератору', 'info')
        
        return redirect(url_for('main.view_report', report_id=report.id))
    
    return render_template('reports/new.html')

@bp.route('/<int:report_id>/upvote', methods=['POST'])
@login_required
def upvote_report(report_id):
    """Поддержать репорт (лайк)"""
    report = Report.query.get_or_404(report_id)
    report.upvotes += 1
    db.session.commit()
    
    return jsonify({'success': True, 'upvotes': report.upvotes})

@bp.route('/<int:report_id>/mark_cleaned', methods=['POST'])
@login_required
def mark_cleaned(report_id):
    """Отметить репорт как убранный (с фото после)"""
    report = Report.query.get_or_404(report_id)
    
    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Необходимо прикрепить фото'}), 400
    
    file = request.files['photo']
    
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Недопустимый файл'}), 400
    
    # Сохраняем фото "после"
    filename = secure_filename(file.filename)
    unique_filename = f"cleaned_{uuid.uuid4().hex}_{filename}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filepath)
    
    # Обновляем репорт
    report.status = 'cleaned'
    report.cleaned_at = datetime.utcnow()
    report.cleaned_photo_path = unique_filename
    report.cleaned_by_id = current_user.id
    
    # Начисляем бонусные баллы автору репорта
    if report.author:
        report.author.add_points(current_app.config['POINTS_CLEANED_REPORT'])
        
        # Уведомление
        notification = Notification(
            user_id=report.author.id,
            message=f'Отличная новость! Ваш репорт #{report.id} убран. +{current_app.config["POINTS_CLEANED_REPORT"]} баллов!',
            notification_type='report_cleaned',
            related_report_id=report.id
        )
        db.session.add(notification)
    
    # Баллы волонтеру
    current_user.add_points(current_app.config['POINTS_CLEANED_REPORT'])
    
    db.session.commit()
    
    flash('Спасибо за уборку! Вам начислены баллы.', 'success')
    return jsonify({'success': True})

@bp.route('/my')
@login_required
def my_reports():
    """Список репортов текущего пользователя"""
    reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc())\
        .all()
    
    return render_template('reports/my_reports.html', reports=reports)

