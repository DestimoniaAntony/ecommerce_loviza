"""
Django settings for commercehub project.
Enterprise Multi-Tenant Multi-Vendor E-Commerce SaaS Platform
"""
import os
from pathlib import Path
from decouple import config, Csv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY', default='django-insecure-%y6fw8^6arlrauey@(5(=s$y#kl(yj)&z6uibe2s51^0v00(kk')
DEBUG = False  
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*', cast=Csv())

# ─────────────────────────────────────────────
# CUSTOM USER MODEL
# ─────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.User'

# ─────────────────────────────────────────────
# INSTALLED APPS
# ─────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party Apps
    'mptt',

    # CommerceHub Core
    'core',
    'accounts',
    'tenants',
    'branches',
    'adminapp',
    'commercehub_app',
    'catalog',
    'inventory',
    'storefront',
    'crm',
]

# ─────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.TenantMiddleware',
    'core.middleware.GeoCurrencyMiddleware',
    'core.middleware.TimezoneMiddleware',
]

ROOT_URLCONF = 'commercehub.urls'

# ─────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.tenant_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'commercehub.wsgi.application'

# ─────────────────────────────────────────────
# DATABASE (SQLite for development)
# ─────────────────────────────────────────────
DATABASES = {
    'default': config(
        'DATABASE_URL',
        default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'),
        cast=dj_database_url.parse
    )
}

# ─────────────────────────────────────────────
# AUTHENTICATION BACKENDS
# ─────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'accounts.backends.PhonePasswordBackend',
    'accounts.backends.PhoneOTPBackend',
    'accounts.backends.EmailPasswordBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ─────────────────────────────────────────────
# PASSWORD VALIDATION
# ─────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─────────────────────────────────────────────
# INTERNATIONALIZATION
# ─────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────
# STATIC & MEDIA FILES
# ─────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ─────────────────────────────────────────────
# DEFAULT AUTO FIELD
# ─────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─────────────────────────────────────────────
# SESSION SETTINGS
# ─────────────────────────────────────────────
SESSION_COOKIE_AGE = 86400 * 7          # 7 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ─────────────────────────────────────────────
# SECURITY HEADERS (production-ready)
# ─────────────────────────────────────────────
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)

# ─────────────────────────────────────────────
# OTP SETTINGS
# ─────────────────────────────────────────────
OTP_EXPIRY_MINUTES = 10
OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 5
OTP_BACKEND = 'console'  # Options: 'console', 'twilio', 'msg91', 'fast2sms'

# ─────────────────────────────────────────────
# EMAIL SETTINGS
# ─────────────────────────────────────────────
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@commercehub.in')

# ─────────────────────────────────────────────
# ACCOUNT SECURITY
# ─────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 30

# ─────────────────────────────────────────────
# PLATFORM SETTINGS
# ─────────────────────────────────────────────
PLATFORM_NAME = 'CommerceHub'
PLATFORM_DOMAIN = config('PLATFORM_DOMAIN', default='localhost')
TRIAL_DAYS = 14

# ─────────────────────────────────────────────
# UPLOAD SETTINGS
# ─────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB in bytes
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB in bytes
