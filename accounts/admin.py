from django.contrib import admin
from .models import User, OTPVerification, LoginHistory


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['phone', 'email', 'first_name', 'last_name', 'user_type', 'is_active', 'date_joined']
    list_filter = ['user_type', 'is_active', 'is_super_admin']
    search_fields = ['phone', 'email', 'first_name', 'last_name']
    readonly_fields = ['date_joined', 'last_login']


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ['phone', 'purpose', 'is_verified', 'attempts', 'created_at', 'expires_at']
    list_filter = ['purpose', 'is_verified']
    search_fields = ['phone']


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ['phone', 'status', 'ip_address', 'created_at']
    list_filter = ['status']
    search_fields = ['phone', 'ip_address']
    readonly_fields = ['created_at']
