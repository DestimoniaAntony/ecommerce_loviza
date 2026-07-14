from django.urls import path
from . import views

app_name = 'branches'

urlpatterns = [
    # Branches
    path('', views.BranchListView.as_view(), name='branch_list'),
    path('create/', views.BranchCreateView.as_view(), name='branch_create'),
    path('<int:branch_id>/edit/', views.BranchEditView.as_view(), name='branch_edit'),
    path('<int:branch_id>/delete/', views.BranchDeleteView.as_view(), name='branch_delete'),

    # Partners
    path('partner/create/', views.PartnerCreateView.as_view(), name='partner_create'),
    path('partner/<int:partner_id>/edit/', views.PartnerEditView.as_view(), name='partner_edit'),
    path('partner/<int:partner_id>/delete/', views.PartnerDeleteView.as_view(), name='partner_delete'),

    # Franchise
    path('franchise/create/', views.FranchiseCreateView.as_view(), name='franchise_create'),
]
