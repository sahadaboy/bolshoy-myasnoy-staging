from django.urls import path
from .cart_api import CartView
from . import api
from . import order_api
from . import experience_api

urlpatterns = [
    path('categories/', api.CategoryListView.as_view()),
    path('banners/', api.BannerListView.as_view()),
    path('storefront/', api.StorefrontView.as_view()),
    path('store/', experience_api.StoreProfileView.as_view()),
    path('dinner/schema/', experience_api.DinnerSchemaView.as_view()),
    path('dinner/suggestions/', experience_api.DinnerSuggestionsView.as_view()),
    path('dinner/prepare/', experience_api.DinnerPrepareView.as_view()),
    path('products/<int:pk>/', api.ProductDetailView.as_view()),
    path('ideas/', api.IdeasView.as_view()),
    path('ideas/<slug:slug>/', api.ArticleDetailView.as_view()),
    path('session/', order_api.SessionView.as_view()),
    path('profile/', order_api.CustomerProfileView.as_view()),
    path('session/login/', order_api.SessionLoginView.as_view()),
    path('cart/', CartView.as_view()),
    path('orders/', order_api.OrderListCreateView.as_view()),
    path('orders/<uuid:order_id>/', order_api.OrderDetailView.as_view()),
    path('orders/<uuid:order_id>/repeat/', order_api.RepeatOrderView.as_view()),
]
