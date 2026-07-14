"""
Django settings for commercehub project.
Enterprise Multi-Tenant Multi-Vendor E-Commerce SaaS Platform
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────
SECRET_KEY = 'django-insecure-%y6fw8^6arlrauey@(5(=s$y#kl(yj)&z6uibe2s51^0v00(kk'
DEBUG = True
ALLOWED_HOSTS = ['*']

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
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.TenantMiddleware',
    'core.middleware.GeoCurrencyMiddleware',
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
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
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
SESSION_COOKIE_SECURE = False           # Set True in production (HTTPS)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ─────────────────────────────────────────────
# SECURITY HEADERS (production-ready)
# ─────────────────────────────────────────────
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# ─────────────────────────────────────────────
# OTP SETTINGS
# ─────────────────────────────────────────────
OTP_EXPIRY_MINUTES = 10
OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 5
OTP_BACKEND = 'console'  # Options: 'console', 'twilio', 'msg91', 'fast2sms'

# ─────────────────────────────────────────────
# EMAIL SETTINGS (configure per vendor via DB)
# ─────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@commercehub.in'

# ─────────────────────────────────────────────
# ACCOUNT SECURITY
# ─────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 30

# ─────────────────────────────────────────────
# PLATFORM SETTINGS
# ─────────────────────────────────────────────
PLATFORM_NAME = 'CommerceHub'
PLATFORM_DOMAIN = 'localhost'
TRIAL_DAYS = 14
