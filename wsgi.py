"""
WSGI entry point for TazaQala application
Используется для запуска через Gunicorn на production сервере
"""
from app import create_app

# Создаем приложение
app = create_app()

# WSGI middleware для обработки подпути /taza_qala
class ScriptNameMiddleware:
    """Middleware для установки SCRIPT_NAME из заголовка X-Script-Name"""
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        # Получаем SCRIPT_NAME из заголовка X-Script-Name
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            # Устанавливаем SCRIPT_NAME в environ (обязательно!)
            environ['SCRIPT_NAME'] = script_name
            # Удаляем префикс из PATH_INFO, если он там есть
            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
                if not environ['PATH_INFO']:
                    environ['PATH_INFO'] = '/'
            # Также устанавливаем в Flask config для url_for
            # Это делается через before_request в app/__init__.py
        
        return self.app(environ, start_response)

# Оборачиваем приложение в middleware
app.wsgi_app = ScriptNameMiddleware(app.wsgi_app)

if __name__ == "__main__":
    app.run()

