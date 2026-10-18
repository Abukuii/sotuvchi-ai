from django.http import HttpResponse
from django.urls import path

# Vaqtinchalik: veb panel keyingi bosqichda yoziladi.
urlpatterns = [
    path("", lambda request: HttpResponse("Sotuvchi AI"), name="dashboard"),
    path("login/", lambda request: HttpResponse("login"), name="login"),
]
