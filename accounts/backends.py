"""
Authentication Backends — CommerceHub

Provides three custom authentication backends:
  1. PhonePasswordBackend — Authenticate via phone + password (super admin / staff)
  2. PhoneOTPBackend      — Authenticate via phone after OTP has been verified
  3. EmailPasswordBackend — Authenticate via email + password (fallback)
"""
from django.contrib.auth.backends import BaseBackend
from .models import User


class PhonePasswordBackend(BaseBackend):
    """
    Authenticates a user by phone number + password.
    Used for Super Admin and vendor staff who set a password.
    """

    def authenticate(self, request, phone=None, password=None, **kwargs):
        if not phone or not password:
            return None
        try:
            user = User.objects.get(phone=phone, is_active=True)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            pass
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class PhoneOTPBackend(BaseBackend):
    """
    Authenticates a user by phone number after OTP has been verified.
    The view sets 'otp_verified=True' after confirming the OTP, then calls authenticate().
    """

    def authenticate(self, request, phone=None, otp_verified=False, **kwargs):
        if not phone or not otp_verified:
            return None
        try:
            user = User.objects.get(phone=phone, is_active=True)
            return user
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class EmailPasswordBackend(BaseBackend):
    """
    Authenticates a user via email + password combination.
    Fallback for users who prefer email-based login.
    """

    def authenticate(self, request, email=None, password=None, **kwargs):
        if not email or not password:
            return None
        try:
            user = User.objects.get(email=email, is_active=True)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            pass
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
