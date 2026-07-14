from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Super Admin auth
    path('admin/login/', views.AdminLoginView.as_view(), name='admin_login'),

    # Vendor staff OTP auth
    path('login/', views.VendorLoginView.as_view(), name='vendor_login'),
    path('login/verify-otp/', views.OTPVerifyView.as_view(), name='otp_verify'),
    path('login/resend-otp/', views.ResendOTPView.as_view(), name='resend_otp'),

    # Logout
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Role Management
    path('roles/', views.RoleListView.as_view(), name='role_list'),
    path('roles/create/', views.RoleCreateView.as_view(), name='role_create'),
    path('roles/<int:role_id>/edit/', views.RoleEditView.as_view(), name='role_edit'),

    # Staff Management
    path('staff/', views.StaffListView.as_view(), name='staff_list'),
    path('staff/create/', views.StaffCreateView.as_view(), name='staff_create'),
    path('staff/<int:staff_id>/edit/', views.StaffEditView.as_view(), name='staff_edit'),
]
