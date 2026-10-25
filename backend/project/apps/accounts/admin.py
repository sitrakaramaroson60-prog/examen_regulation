from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "role", "organization", "is_active"]
    list_filter = ["role", "organization", "is_active"]
    search_fields = ["email"]
    exclude = ["password", "user_permissions", "groups"]
