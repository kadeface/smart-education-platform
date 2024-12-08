import os
from django.core.wsgi import get_wsgi_application
# wsgi.py 或 asgi.py 文件中的设置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'score_analysis_project.settings')
application = get_wsgi_application()