"""Routes du projet (propriétaire : Rôle 2)."""
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView
from strawberry.django.views import GraphQLView

from tunisovereign_core.api_rest import LoginView, RegisterView, router
from tunisovereign_core.schema_graphql import schema
from django.views.decorators.csrf import csrf_exempt

urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', GraphQLView.as_view(schema=schema)),
]