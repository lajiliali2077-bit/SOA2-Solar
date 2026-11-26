from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenRefreshView
from strawberry.django.views import GraphQLView

from tunisovereign_core.api_rest import LoginView, RegisterView, router
from tunisovereign_core.schema_graphql import schema

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/register/", RegisterView.as_view(), name="auth-register"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("api/v1/", include(router.urls)),
    path("graphql/", csrf_exempt(GraphQLView.as_view(schema=schema))),
]