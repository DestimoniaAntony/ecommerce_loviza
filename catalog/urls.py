from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    # Categories
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/create/', views.CategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:category_id>/edit/', views.CategoryEditView.as_view(), name='category_edit'),
    path('categories/<int:category_id>/delete/', views.CategoryDeleteView.as_view(), name='category_delete'),

    # Attributes
    path('attributes/', views.AttributeListView.as_view(), name='attribute_list'),
    path('attributes/group/create/', views.AttributeGroupCreateView.as_view(), name='attribute_group_create'),
    path('attributes/group/<int:group_id>/edit/', views.AttributeGroupEditView.as_view(), name='attribute_group_edit'),
    path('attributes/group/<int:group_id>/delete/', views.AttributeGroupDeleteView.as_view(), name='attribute_group_delete'),
    path('attributes/create/', views.AttributeCreateView.as_view(), name='attribute_create'),
    path('attributes/<int:attribute_id>/edit/', views.AttributeEditView.as_view(), name='attribute_edit'),
    path('attributes/<int:attribute_id>/delete/', views.AttributeDeleteView.as_view(), name='attribute_delete'),

    # Products
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/create/', views.ProductCreateView.as_view(), name='product_create'),
    path('products/<int:product_id>/edit/', views.ProductEditView.as_view(), name='product_edit'),
    path('products/<int:product_id>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),
]
