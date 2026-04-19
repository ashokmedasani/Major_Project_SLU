from django.contrib.auth.decorators import user_passes_test


def developer_approved_required(view_func):
    def check(user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        profile = getattr(user, "developer_profile", None)
        return bool(profile and profile.is_approved)

    return user_passes_test(check, login_url="developer_login")(view_func)