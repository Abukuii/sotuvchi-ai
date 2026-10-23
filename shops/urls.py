from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .auth_views import ThrottledLoginView

urlpatterns = [
    path("", views.landing, name="landing"),
    path("panel/", views.dashboard, name="dashboard"),
    path("login/", ThrottledLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", views.password_change, name="password_change"),
    path("signup/", views.signup, name="signup"),
    path("security/", views.security, name="security"),
    path("security/revoke-sessions/", views.revoke_sessions, name="revoke_sessions"),
    path("settings/", views.shop_settings, name="shop_settings"),
    path("settings/regenerate-link/", views.regenerate_link, name="regenerate_link"),
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/upload/", views.catalog_upload, name="catalog_upload"),
    path("catalog/template.xlsx", views.catalog_template, name="catalog_template"),
    path("catalog/new/", views.product_edit, name="product_new"),
    path("catalog/<int:pk>/", views.product_edit, name="product_edit"),
    path("catalog/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("orders/live/", views.live_state, name="live_state"),
    path("orders/", views.orders, name="orders"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/status/", views.order_status, name="order_status"),
    path("conversations/", views.conversations, name="conversations"),
    path("conversations/<int:pk>/", views.conversation_detail, name="conversation_detail"),
    path("conversations/<int:pk>/delete/", views.conversation_delete, name="conversation_delete"),
]
