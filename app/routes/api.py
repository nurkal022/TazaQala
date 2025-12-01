from flask import Blueprint, jsonify, request
from app.models import Report, User
from sqlalchemy import func

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/reports')
def get_reports():
    """API для получения репортов (для карты)"""
    status = request.args.get('status', '')
    district = request.args.get('district')
    limit = request.args.get('limit', 500, type=int)
    
    # Границы Алматы (расширенные для включения всех репортов)
    ALMATY_LAT_MIN = 42.8
    ALMATY_LAT_MAX = 43.5
    ALMATY_LON_MIN = 76.4
    ALMATY_LON_MAX = 77.3
    
    query = Report.query.filter(
        Report.latitude >= ALMATY_LAT_MIN,
        Report.latitude <= ALMATY_LAT_MAX,
        Report.longitude >= ALMATY_LON_MIN,
        Report.longitude <= ALMATY_LON_MAX
    )
    
    if status:
        query = query.filter_by(status=status)
    
    if district:
        query = query.filter_by(district=district)
    
    reports = query.order_by(Report.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'reports': [{
            'id': r.id,
            'latitude': r.latitude,
            'longitude': r.longitude,
            'address': r.address,
            'district': r.district,
            'description': r.description,
            'photo_path': r.photo_path,
            'photo_url': f'/static/{r.photo_path}' if r.photo_path and r.photo_path == 'image.png' else (f'/static/uploads/{r.photo_path}' if r.photo_path else None),
            'trash_type': r.trash_type,  # Для обратной совместимости
            'report_category': r.report_category or r.trash_type or 'trash',
            'status': r.status,
            'ai_confidence': r.ai_confidence,
            'is_anonymous': r.is_anonymous,
            'upvotes': r.upvotes,
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'author': (r.author.username if r.author and not r.is_anonymous and not (r.author.is_anonymous_display if r.author and hasattr(r.author, 'is_anonymous_display') else False) else 'Аноним') if r.author else 'Аноним'
        } for r in reports]
    })

@bp.route('/leaderboard')
def get_leaderboard():
    """API для получения лидерборда"""
    limit = request.args.get('limit', 10, type=int)
    district = request.args.get('district')
    
    if district:
        # Лидерборд по району
        users = User.query.join(Report)\
            .filter(Report.district == district)\
            .group_by(User.id)\
            .order_by(func.count(Report.id).desc())\
            .limit(limit)\
            .all()
    else:
        # Общий лидерборд
        users = User.query.filter(User.total_points > 0)\
            .order_by(User.total_points.desc())\
            .limit(limit)\
            .all()
    
    return jsonify({
        'leaderboard': [{
            'rank': idx + 1,
            'username': u.username if not u.is_anonymous_display else f'Пользователь #{u.id}',
            'points': u.total_points,
            'level': u.level,
            'reports_count': u.reports_count,
            'confirmed_reports': u.confirmed_reports
        } for idx, u in enumerate(users)]
    })

@bp.route('/stats')
def get_stats():
    """API для получения общей статистики"""
    total_reports = Report.query.count()
    confirmed_reports = Report.query.filter_by(status='confirmed').count()
    cleaned_reports = Report.query.filter_by(status='cleaned').count()
    pending_reports = Report.query.filter_by(status='pending').count()
    active_users = User.query.filter(User.reports_count > 0).count()
    
    # Статистика по районам
    district_stats = Report.query.with_entities(
        Report.district,
        func.count(Report.id).label('total'),
        func.sum(func.case([(Report.status == 'cleaned', 1)], else_=0)).label('cleaned')
    ).group_by(Report.district).all()
    
    # Статистика AI
    ai_auto_confirmed = Report.query.filter_by(ai_status='auto_confirmed').count()
    ai_needs_review = Report.query.filter_by(ai_status='needs_review').count()
    
    return jsonify({
        'total_reports': total_reports,
        'confirmed_reports': confirmed_reports,
        'cleaned_reports': cleaned_reports,
        'pending_reports': pending_reports,
        'active_users': active_users,
        'ai_accuracy': round(ai_auto_confirmed / max(total_reports, 1) * 100, 1),
        'districts': [{
            'name': d[0],
            'total': d[1],
            'cleaned': d[2],
            'cleanup_rate': round(d[2] / max(d[1], 1) * 100, 1)
        } for d in district_stats if d[0]]
    })

@bp.route('/report/<int:report_id>')
def get_report(report_id):
    """API для получения конкретного репорта"""
    report = Report.query.get_or_404(report_id)
    
    return jsonify({
        'id': report.id,
        'latitude': report.latitude,
        'longitude': report.longitude,
        'address': report.address,
        'district': report.district,
        'description': report.description,
        'photo_url': f'/static/uploads/{report.photo_path}',
        'cleaned_photo_url': f'/static/img_after.jpeg' if (not report.cleaned_photo_path or report.cleaned_photo_path == 'img_after.jpeg') else (f'/static/{report.cleaned_photo_path}' if report.cleaned_photo_path == 'img_after.jpeg' else f'/static/uploads/{report.cleaned_photo_path}'),
        'trash_type': report.trash_type,  # Для обратной совместимости
        'report_category': report.report_category or report.trash_type or 'trash',
        'status': report.status,
        'ai_confidence': report.ai_confidence,
        'ai_status': report.ai_status,
        'upvotes': report.upvotes,
        'views_count': report.views_count,
        'created_at': report.created_at.isoformat(),
        'cleaned_at': report.cleaned_at.isoformat() if report.cleaned_at else None,
        'author': report.author.username if report.author and not report.author.is_anonymous_display else 'Аноним'
    })

