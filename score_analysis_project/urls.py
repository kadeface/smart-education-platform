from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('score-analysis/', include('score_analysis.urls')),
    path('score-processor/', include('score_processor.urls')),
]
