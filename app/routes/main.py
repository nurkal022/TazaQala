from flask import Blueprint, render_template, request, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import Report, User, Reward, RewardRedemption, Notification
from sqlalchemy import func, case

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Главная страница - landing page"""
    # Статистика для главной
    total_reports = Report.query.count()
    cleaned_reports = Report.query.filter_by(status='cleaned').count()
    active_users = User.query.filter(User.reports_count > 0).count()
    pending_reports = Report.query.filter_by(status='pending').count()
    
    stats = {
        'total_reports': total_reports,
        'cleaned_reports': cleaned_reports,
        'active_users': active_users,
        'pending_reports': pending_reports
    }
    
    return render_template('home.html', stats=stats)

@bp.route('/map')
def map():
    """Страница с картой загрязнений"""
    # Статистика для фильтров
    stats = {
        'total_reports': Report.query.count(),
        'confirmed': Report.query.filter_by(status='confirmed').count(),
        'cleaned': Report.query.filter_by(status='cleaned').count(),
        'pending': Report.query.filter_by(status='pending').count()
    }
    
    return render_template('map.html', stats=stats)

@bp.route('/about')
def about():
    """О проекте"""
    return render_template('about.html')

@bp.route('/leaderboard')
def leaderboard():
    """Лидерборд"""
    # ТОП-10 пользователей по городу
    top_users = User.query.filter(User.total_points > 0)\
        .order_by(User.total_points.desc())\
        .limit(10)\
        .all()
    
    # ТОП по районам (пример для Алмалинского)
    districts = ['Алмалинский', 'Ауэзовский', 'Бостандыкский', 'Жетысуский', 
                 'Медеуский', 'Наурызбайский', 'Турксибский', 'Алатауский']
    
    district_leaders = {}
    for district in districts:
        # Получаем топ-3 пользователей по району (исправлено: указываем явный join)
        district_top = User.query.join(Report, User.id == Report.user_id)\
            .filter(Report.district == district)\
            .group_by(User.id)\
            .order_by(func.count(Report.id).desc())\
            .limit(3)\
            .all()
        district_leaders[district] = district_top
    
    return render_template('leaderboard.html', 
                         top_users=top_users,
                         district_leaders=district_leaders)


@bp.route('/rewards')
def rewards():
    """Каталог призов"""
    rewards = Reward.query.filter_by(is_active=True)\
        .order_by(Reward.cost_points.asc(), Reward.created_at.desc())\
        .all()

    recent_redemptions = []
    user_balance = 0
    if current_user.is_authenticated:
        user_balance = current_user.points_balance
        recent_redemptions = RewardRedemption.query.filter_by(user_id=current_user.id)\
            .order_by(RewardRedemption.created_at.desc())\
            .limit(5)\
            .all()

    return render_template(
        'rewards.html',
        rewards=rewards,
        user_balance=user_balance,
        recent_redemptions=recent_redemptions
    )


@bp.route('/rewards/<int:reward_id>/redeem', methods=['POST'])
@login_required
def redeem_reward(reward_id):
    """Запрос на получение приза"""
    reward = Reward.query.get_or_404(reward_id)

    if not reward.is_available():
        flash('Этот приз временно недоступен', 'warning')
        return redirect(url_for('main.rewards'))

    if current_user.points_balance < reward.cost_points:
        flash('Недостаточно баллов для этого приза', 'danger')
        return redirect(url_for('main.rewards'))

    try:
        current_user.points_balance -= reward.cost_points
        current_user.points_spent += reward.cost_points
        reward.redeemed_count += 1

        redemption = RewardRedemption(
            user_id=current_user.id,
            reward_id=reward.id,
            points_spent=reward.cost_points,
            status='pending'
        )
        db.session.add(redemption)

        notification = Notification(
            user_id=current_user.id,
            message=f'Заявка на приз "{reward.title}" отправлена. Мы свяжемся с вами для вручения!',
            notification_type='reward_requested'
        )
        db.session.add(notification)

        db.session.commit()
        flash('Заявка отправлена! Мы свяжемся с вами в ближайшее время.', 'success')
    except Exception:
        db.session.rollback()
        flash('Не удалось оформить заявку, попробуйте позже.', 'danger')

    return redirect(url_for('main.rewards'))


@bp.route('/report/<int:report_id>')
def view_report(report_id):
    """Просмотр конкретного репорта"""
    report = Report.query.get_or_404(report_id)
    
    # Увеличиваем счетчик просмотров
    report.views_count += 1
    from app import db
    db.session.commit()
    
    return render_template('report_detail.html', report=report)

