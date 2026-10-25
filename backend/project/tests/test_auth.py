import pytest
from datetime import timedelta
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role, User
from apps.organizations.models import Organization

from .conftest import PASSWORD, client_for, make_user

LOGIN = "/api/v1/auth/login/"


def test_login_valid(anon, yas):
    r = anon.post(LOGIN, {"email": yas.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200
    assert {"access", "refresh", "user"} <= set(r.data)
    assert r.data["user"]["organization"]["code"] == "YAS"
    assert r.data["user"]["space"] == "operator"


def test_login_wrong_password(anon, yas):
    r = anon.post(LOGIN, {"email": yas.email, "password": "mauvais"}, format="json")
    assert r.status_code == 401
    assert r.data["error"]["code"] == "authentication_failed"


def test_login_unknown_email_same_message(anon, yas):
    a = anon.post(LOGIN, {"email": "nobody@test.mg", "password": "x"}, format="json")
    b = anon.post(LOGIN, {"email": yas.email, "password": "x"}, format="json")
    assert a.status_code == b.status_code == 401
    assert a.data["error"]["message"] == b.data["error"]["message"]


def test_login_disabled_account(anon, yas):
    yas.is_active = False
    yas.save()
    assert anon.post(LOGIN, {"email": yas.email, "password": PASSWORD}, format="json").status_code == 401


def test_bruteforce_lockout(anon, yas):
    for _ in range(5):
        anon.post(LOGIN, {"email": yas.email, "password": "bad"}, format="json")
    r = anon.post(LOGIN, {"email": yas.email, "password": PASSWORD}, format="json")
    assert r.status_code == 401  # verrouillé même avec le bon mot de passe


def test_anonymous_cannot_access_private_endpoint(anon):
    assert anon.get("/api/v1/auth/me/").status_code == 401
    assert anon.get("/api/v1/datasets/").status_code == 401


def test_expired_token_rejected(anon, yas):
    token = AccessToken.for_user(yas)
    token.set_exp(lifetime=-timedelta(seconds=10))
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert anon.get("/api/v1/auth/me/").status_code == 401


def test_deactivated_user_token_rejected(anon, yas):
    token = str(AccessToken.for_user(yas))
    yas.is_active = False
    yas.save()
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert anon.get("/api/v1/auth/me/").status_code == 401


def test_me_and_logout_blacklists_refresh(anon, yas):
    r = anon.post(LOGIN, {"email": yas.email, "password": PASSWORD}, format="json")
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert anon.get("/api/v1/auth/me/").data["email"] == yas.email
    assert anon.post("/api/v1/auth/logout/", {"refresh": r.data["refresh"]}, format="json").status_code == 204
    anon.credentials()
    assert anon.post("/api/v1/auth/refresh/", {"refresh": r.data["refresh"]}, format="json").status_code == 401


def test_change_password_revokes_tokens(anon, yas):
    r = anon.post(LOGIN, {"email": yas.email, "password": PASSWORD}, format="json")
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    ok = anon.post("/api/v1/auth/change-password/", {"old_password": PASSWORD, "new_password": "An0ther-Str0ng-Pass!"}, format="json")
    assert ok.status_code == 204
    assert anon.get("/api/v1/auth/me/").status_code == 401  # ancien access invalidé
    assert anon.post("/api/v1/auth/refresh/", {"refresh": r.data["refresh"]}, format="json").status_code == 401


def test_change_password_rejects_weak(api, yas):
    r = api(yas).post("/api/v1/auth/change-password/", {"old_password": PASSWORD, "new_password": "123"}, format="json")
    assert r.status_code == 400


def test_no_public_registration(anon):
    assert anon.post("/api/v1/auth/register/", {"email": "x@y.mg", "password": "x"}, format="json").status_code == 404


def test_user_cannot_escalate_role(api, yas):
    c = api(yas)
    assert c.patch("/api/v1/auth/users/%d/" % yas.pk, {"role": "SYSTEM_ADMIN"}, format="json").status_code == 403
    assert c.post("/api/v1/auth/users/", {"email": "n@t.mg", "role": "SYSTEM_ADMIN", "password": PASSWORD}, format="json").status_code == 403
    yas.refresh_from_db()
    assert yas.role == Role.OPERATOR_USER


def test_admin_creates_professional_accounts_with_constraints(api, sysadmin):
    c = api(sysadmin)
    ok = c.post("/api/v1/auth/users/", {"email": "n@t.mg", "role": "OPERATOR_USER", "organization": "ORANGE", "password": PASSWORD}, format="json")
    assert ok.status_code == 201
    bad = c.post("/api/v1/auth/users/", {"email": "m@t.mg", "role": "OPERATOR_USER", "organization": "ARTEC", "password": PASSWORD}, format="json")
    assert bad.status_code == 400
    bad2 = c.post("/api/v1/auth/users/", {"email": "o@t.mg", "role": "ARTEC_REGULATOR", "organization": "YAS", "password": PASSWORD}, format="json")
    assert bad2.status_code == 400


def test_model_level_role_org_constraints(db):
    artec = Organization.objects.get(code="ARTEC")
    with pytest.raises(Exception):
        User.objects.create_user(email="z@t.mg", password=PASSWORD, role=Role.OPERATOR_USER, organization=artec)


def test_init_accounts_command(db, capsys):
    from django.core.management import call_command

    call_command("init_accounts")
    out = capsys.readouterr().out
    assert User.objects.count() == 6
    assert set(User.objects.values_list("role", flat=True)) == {"OPERATOR_USER", "ARTEC_REGULATOR", "ARTEC_PUBLISHER", "SYSTEM_ADMIN"}
    assert User.objects.filter(role="OPERATOR_USER").count() == 3
    assert User.objects.get(email="artec.regulation@plateforme.local").organization.code == "ARTEC"
    assert not any(u.check_password("") or u.has_usable_password() is False for u in User.objects.all())
    assert "ne seront plus affichés" in out
    call_command("init_accounts")  # idempotent : aucun compte modifié ni dupliqué
    assert User.objects.count() == 6
