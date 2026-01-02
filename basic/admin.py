# basic/admin.py
from django.contrib import admin
from .models import StudentIDMapping


@admin.register(StudentIDMapping)
class StudentIDMappingAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'student_registration', 'current_level']
    search_fields = ['student_name', 'student_registration', 'id_number']
    list_filter = ['current_level']


from django.contrib import admin

# Register your models here.
