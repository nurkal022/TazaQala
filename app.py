"""
TazaQala - Гражданская экоплатформа
Главный файл запуска приложения
"""

from app import create_app, db
from app.models import User, Report, Badge, Notification, Reward

app = create_app()

@app.shell_context_processor
def make_shell_context():
    """Добавляет переменные в shell контекст для удобства работы"""
    return {
        'db': db,
        'User': User,
        'Report': Report,
        'Badge': Badge,
        'Notification': Notification
    }

@app.cli.command()
def init_db():
    """Инициализация базы данных"""
    db.create_all()
    print("✅ База данных инициализирована!")

@app.cli.command()
def create_admin():
    """Создание администратора"""
    from getpass import getpass
    
    username = input("Имя пользователя: ")
    email = input("Email: ")
    password = getpass("Пароль: ")
    
    # Проверка на существующего пользователя
    if User.query.filter_by(username=username).first():
        print("❌ Пользователь с таким именем уже существует!")
        return
    
    if User.query.filter_by(email=email).first():
        print("❌ Email уже используется!")
        return
    
    # Создаем админа
    admin = User(
        username=username,
        email=email,
        role='admin',
        full_name='Администратор'
    )
    admin.set_password(password)
    
    db.session.add(admin)
    db.session.commit()
    
    print(f"✅ Администратор {username} создан успешно!")

@app.cli.command()
def seed_data():
    """Добавление тестовых данных"""
    import random
    
    print("🌱 Начинаю добавление тестовых данных...")
    
    # Проверяем, есть ли уже тестовые пользователи
    existing_users = User.query.filter(User.username.like('user%')).count()
    if existing_users > 0:
        print(f"⚠️  Найдено {existing_users} тестовых пользователей. Пропускаю создание пользователей.")
        users = User.query.filter(User.username.like('user%')).all()
    else:
        # Создаем тестовых пользователей
        print("👥 Создаю тестовых пользователей...")
        users = []
        for i in range(10):
            total_points = random.randint(0, 500)
            user = User(
                username=f'user{i+1}',
                email=f'user{i+1}@example.com',
                full_name=f'Пользователь {i+1}',
                total_points=total_points,
                reports_count=random.randint(0, 50)
            )
            user.set_password('password123')
            user._update_level()
            user.points_balance = user.total_points
            users.append(user)
            db.session.add(user)
        
        db.session.commit()
        print(f"✅ Создано {len(users)} тестовых пользователей")
    
    # Проверяем существующие репорты
    existing_reports = Report.query.count()
    if existing_reports > 0:
        print(f"⚠️  Найдено {existing_reports} репортов. Добавляю ещё...")
    else:
        print("📸 Создаю тестовые репорты...")
    
    # Создаем тестовые репорты
    districts = ['Алмалинский', 'Ауэзовский', 'Бостандыкский', 'Жетысуский', 
                 'Медеуский', 'Наурызбайский', 'Турксибский', 'Алатауский']
    trash_types = ['plastic', 'metal', 'organic', 'mixed', 'construction', 'paper']
    statuses = ['confirmed', 'pending', 'cleaned', 'rejected']
    addresses = [
        'ул. Абая', 'ул. Сатпаева', 'пр. Достык', 'ул. Толе би',
        'ул. Гоголя', 'пр. Аль-Фараби', 'ул. Жибек Жолы', 'ул. Байтурсынова'
    ]
    
    # Используем существующие фото или создаём путь к плейсхолдеру
    upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
    placeholder_path = 'placeholder.jpg'
    
    # Проверяем наличие реальных фото
    if os.path.exists(upload_folder):
        existing_photos = [f for f in os.listdir(upload_folder) if f.endswith(('.jpg', '.jpeg', '.png'))]
        if existing_photos:
            placeholder_path = os.path.join('uploads', random.choice(existing_photos))
    
    reports_created = 0
    for i in range(50):
        # Случайная дата в последние 30 дней
        days_ago = random.randint(0, 30)
        created_date = datetime.utcnow() - timedelta(days=days_ago)
        
        # Выбираем случайного пользователя
        user = random.choice(users) if users else None
        
        # Генерируем координаты в пределах Алматы
        lat = 43.2220 + random.uniform(-0.15, 0.15)
        lon = 76.8512 + random.uniform(-0.15, 0.15)
        
        # Выбираем статус и связанные данные
        status = random.choice(statuses)
        ai_status = 'auto_confirmed' if status == 'confirmed' else random.choice(['needs_review', 'rejected'])
        ai_confidence = random.uniform(0.6, 0.98) if ai_status == 'auto_confirmed' else random.uniform(0.3, 0.85)
        
        report = Report(
            user_id=user.id if user else None,
            is_anonymous=random.choice([True, False]) if not user else False,
            latitude=lat,
            longitude=lon,
            district=random.choice(districts),
            address=f'{random.choice(addresses)}, д. {random.randint(1, 200)}',
            description=random.choice([
                f'Обнаружено скопление мусора возле дома',
                f'Большая свалка на обочине дороги',
                f'Мусорные контейнеры переполнены',
                f'Разбросанный мусор в парке',
                f'Строительный мусор на тротуаре',
                f'Пластиковые бутылки и упаковка',
                f'Органические отходы',
                f'Смешанный мусор'
            ]),
            photo_path=placeholder_path,
            trash_type=random.choice(trash_types),
            status=status,
            ai_confidence=ai_confidence,
            ai_status=ai_status,
            upvotes=random.randint(0, 50),
            views_count=random.randint(0, 200),
            created_at=created_date
        )
        db.session.add(report)
        reports_created += 1
    
    db.session.commit()
    # Создаем подарки, если их еще нет
    if Reward.query.count() == 0:
        rewards_seed = [
            {
                'title': 'Эко-набор «Зелёный старт»',
                'description': 'Многоразовый шоппер, бутылка и набор для сортировки.',
                'cost_points': 80,
                'image_path': None,
                'category': 'eco',
                'total_quantity': 15
            },
            {
                'title': 'Серприст на посадку дерева',
                'description': 'Сертификат на участие в посадке деревьев с командой TazaQala.',
                'cost_points': 120,
                'image_path': None,
                'category': 'experience',
                'total_quantity': 10
            },
            {
                'title': 'Цифровой бейдж «Герой района»',
                'description': 'Эксклюзивный бейдж в профиль и упоминание на главной странице.',
                'cost_points': 60,
                'image_path': None,
                'category': 'digital',
                'total_quantity': None
            }
        ]
        for payload in rewards_seed:
            db.session.add(Reward(**payload))
        db.session.commit()
        print("🎁 Добавлены базовые призы")
    
    # Обновляем статистику пользователей
    print("📊 Обновляю статистику пользователей...")
    for user in users:
        user.reports_count = Report.query.filter_by(user_id=user.id).count()
        user.confirmed_reports = Report.query.filter_by(user_id=user.id, status='confirmed').count()
        user.rejected_reports = Report.query.filter_by(user_id=user.id, status='rejected').count()
    
    db.session.commit()
    
    print(f"✅ Тестовые данные добавлены!")
    print(f"   👥 Пользователей: {len(users)}")
    print(f"   📸 Репортов создано: {reports_created}")
    print(f"   📊 Всего репортов в БД: {Report.query.count()}")
    print("\n💡 Тестовые пользователи:")
    print("   Логин: user1, user2, ..., user10")
    print("   Пароль: password123")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
