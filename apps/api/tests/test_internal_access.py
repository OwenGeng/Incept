import pytest
from fastapi import HTTPException

from app.routers import internal
from app.services import auth as service_auth


class _NoAccessRecordService:
    def get_user_record(self, _email: str):
        return None


def test_moloco_user_without_explicit_record_gets_admin_role(monkeypatch):
    monkeypatch.setattr(internal, "_service", _NoAccessRecordService())

    assert internal.check_access("person@moloco.com") == {
        "role": "admin",
        "allowed_projects": None,
    }


def test_internal_auth_fails_closed_when_production_key_is_missing(monkeypatch):
    monkeypatch.setattr(service_auth.settings, "incept_env", "production")
    monkeypatch.setattr(service_auth.settings, "internal_api_key", "")

    with pytest.raises(HTTPException) as error:
        service_auth.require_internal_key("")

    assert error.value.status_code == 503
