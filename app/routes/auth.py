from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from app import db
from app.models import User
from datetime import datetime

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        password2 = request.form.get('password2')
        full_name = request.form.get('full_name')
        
        # Валидация
        errors = []
        
        if not username or len(username) < 3:
            errors.append('Имя пользователя должно содержать минимум 3 символа')
        
        if not email or '@' not in email:
            errors.append('Введите корректный email')
        
        if not password or len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов')
        
        if password != password2:
            errors.append('Пароли не совпадают')
        
        # Проверка на существующего пользователя
        if User.query.filter_by(username=username).first():
            errors.append('Пользователь с таким именем уже существует')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email уже используется')
        
        if phone and User.query.filter_by(phone=phone).first():
            errors.append('Телефон уже используется')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html')
        
        # Создаем пользователя
        user = User(
            username=username,
            email=email,
            phone=phone,
            full_name=full_name
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в систему"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Неверное имя пользователя или пароль', 'danger')
            return render_template('auth/login.html')
        
        # Обновляем время последнего входа
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=remember)
        
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('main.index')
        
        flash(f'Добро пожаловать, {user.username}!', 'success')
        return redirect(next_page)
    
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('main.index'))

@bp.route('/profile')
@login_required
def profile():
    """Личный кабинет"""
    # Получаем репорты пользователя
    user_reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc())\
        .limit(20)\
        .all()
    
    # Получаем бейджи
    badges = current_user.badges
    
    # Получаем место в рейтинге
    users_above = User.query.filter(User.total_points > current_user.total_points).count()
    rank = users_above + 1
    
    return render_template('auth/profile.html',
                         reports=user_reports,
                         badges=badges,
                         rank=rank)

@bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Редактирование профиля"""
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.phone = request.form.get('phone')
        current_user.is_anonymous_display = request.form.get('is_anonymous_display') == 'on'
        
        db.session.commit()
        flash('Профиль обновлен', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/edit_profile.html')

# Import Report model here to avoid circular import
from app.models import Report

