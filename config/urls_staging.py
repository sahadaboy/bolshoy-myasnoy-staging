from django.urls import path, re_path, include
from django.contrib import admin
from shop.api import ProductListView
from deploy.web import health, spa

urlpatterns = [
    path('healthz', health),
    path('admin/', admin.site.urls),
    path('api/', include('storefront.urls')),
    path('api/products/', ProductListView.as_view()),
    re_path(r'^(?:catalog|about(?:/map)?|ideas(?:/dinner|/article/[a-z0-9_-]+|/recipes|/collections)?|cart|checkout|profile(?:/orders(?:/[a-f0-9-]{36}(?:/success)?)?|/store|/about|/contacts|/help)?|product/[1-9]\d*)?/?$', spa),
]
