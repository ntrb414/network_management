from django.urls import path
from . import views

app_name = 'homepage'

urlpatterns = [
    path('', views.HomepageView.as_view(), name='homepage'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]
