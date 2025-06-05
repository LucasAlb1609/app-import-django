from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Rota raiz (homepage) aponta para a view de login
    path("", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    # Rota para a página de cadastro
    path("signup/", views.SignUpView.as_view(), name="signup"),
    # Rota para a página inicial após o login (onde fica o upload)
    path("home/", views.home, name="home"),
    # Rota para listar os editais carregados
    path("editais/", views.listar_editais, name="listar_editais"),
    # Rota para detalhes e filtros de um edital específico
    path("editais/<int:edital_id>/", views.detalhe_edital, name="detalhe_edital"),
    # Rota para download do CSV de um edital específico
    path("editais/download/<int:edital_id>/", views.download_edital_csv, name="download_edital_csv"),
    # Django já fornece URLs para logout, mudança de senha, etc. em django.contrib.auth.urls
]
