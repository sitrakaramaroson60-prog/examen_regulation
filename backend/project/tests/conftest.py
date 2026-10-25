import io

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.organizations.models import City, Organization, Region

PASSWORD = "Str0ng-Test-Passw0rd!"


@pytest.fixture(autouse=True)
def base_data(db):
    call_command("init_organizations", verbosity=0)
    ana = Region.objects.create(name="Analamanga", code="analamanga")
    vak = Region.objects.create(name="Vakinankaratra", code="vakinankaratra")
    City.objects.create(region=ana, name="Antananarivo")
    City.objects.create(region=vak, name="Antsirabe")


def make_user(email, role, org_code):
    org = Organization.objects.get(code=org_code)
    return User.objects.create_user(email=email, password=PASSWORD, role=role, organization=org)


@pytest.fixture
def yas(db):
    return make_user("yas@test.mg", Role.OPERATOR_USER, "YAS")


@pytest.fixture
def airtel(db):
    return make_user("airtel@test.mg", Role.OPERATOR_USER, "AIRTEL")


@pytest.fixture
def orange(db):
    return make_user("orange@test.mg", Role.OPERATOR_USER, "ORANGE")


@pytest.fixture
def publisher(db):
    return make_user("pub@test.mg", Role.ARTEC_PUBLISHER, "ARTEC")


@pytest.fixture
def regulator(db):
    return make_user("reg@test.mg", Role.ARTEC_REGULATOR, "ARTEC")


@pytest.fixture
def sysadmin(db):
    return make_user("admin@test.mg", Role.SYSTEM_ADMIN, "ARTEC")


def client_for(user=None):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user)
    return c


@pytest.fixture
def anon():
    return client_for()


@pytest.fixture
def api():
    return client_for


def csv_file(text, name="data.csv"):
    f = io.BytesIO(text.encode("utf-8"))
    f.name = name
    return f


QOS_HEADER = "region,city,service_type,technology,metric_name,metric_value,unit,measurement_method,measured_at\n"


def qos_csv(n=5, bad=False):
    rows = [f"Analamanga,Antananarivo,DATA,4G,download_speed,{10 + i},Mbps,speedtest-v1,2026-09-0{(i % 9) + 1}T10:00:00Z" for i in range(n)]
    if bad:
        rows.append("Analamanga,Antananarivo,DATA,4G,download_speed,abc,Mbps,speedtest-v1,2026-09-01T10:00:00Z")
    return QOS_HEADER + "\n".join(rows) + "\n"


@pytest.fixture
def live(django_capture_on_commit_callbacks):
    """Exécute les rappels « après commit » (événements temps réel) dans les tests, qui tournent dans une transaction annulée."""
    from contextlib import contextmanager

    from django.db import connection

    @contextmanager
    def ctx():
        connection.run_on_commit.clear()
        connection._rt_batch = None
        with django_capture_on_commit_callbacks(execute=True):
            yield

    return ctx
