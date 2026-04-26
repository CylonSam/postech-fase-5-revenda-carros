import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Set env vars before the module is loaded
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_testpool"
os.environ["COGNITO_CLIENT_ID"] = "test_client_id"

# Load the lambda module with a mocked boto3 client so the module-level
# `cognito = boto3.client(...)` call gets our mock instead of hitting AWS.
_mock_cognito = MagicMock()
with patch("boto3.client", return_value=_mock_cognito):
    _spec = importlib.util.spec_from_file_location("auth_index", Path(__file__).parent / "index.py")
    auth = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(auth)


def _client_error(code, message="error"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "op")


def _event(route, body=None):
    return {"routeKey": route, "body": json.dumps(body) if body else None}


@pytest.fixture(autouse=True)
def reset():
    _mock_cognito.reset_mock()


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    _valid_body = {
        "email": "alice@example.com",
        "password": "Test123!",
        "name": "Alice",
        "taxId": "12345678901",
        "documentId": "987654321",
        "birthDate": "1990-01-15",
        "address": "123 Main St",
        "phone": "+5511999999999",
        "driversLicenseId": "AB123456",
        "category": "B",
        "expirationDate": "2028-03-01",
    }

    def _without(self, *keys):
        return {k: v for k, v in self._valid_body.items() if k not in keys}

    def test_success_returns_201_and_user_sub(self):
        _mock_cognito.sign_up.return_value = {"UserSub": "sub-abc-123"}

        resp = auth.handler(_event("POST /auth/register", self._valid_body), None)

        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["user_sub"] == "sub-abc-123"
        _mock_cognito.admin_confirm_sign_up.assert_called_once_with(
            UserPoolId="us-east-1_testpool", Username="alice@example.com"
        )

    def test_missing_email_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("email")), None)
        assert resp["statusCode"] == 400

    def test_missing_password_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("password")), None)
        assert resp["statusCode"] == 400

    def test_missing_name_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("name")), None)
        assert resp["statusCode"] == 400

    def test_missing_tax_id_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("taxId")), None)
        assert resp["statusCode"] == 400

    def test_missing_document_id_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("documentId")), None)
        assert resp["statusCode"] == 400

    def test_missing_birth_date_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("birthDate")), None)
        assert resp["statusCode"] == 400

    def test_missing_address_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("address")), None)
        assert resp["statusCode"] == 400

    def test_missing_phone_returns_400(self):
        resp = auth.handler(_event("POST /auth/register", self._without("phone")), None)
        assert resp["statusCode"] == 400

    def test_duplicate_email_returns_409(self):
        _mock_cognito.sign_up.side_effect = _client_error("UsernameExistsException")

        resp = auth.handler(_event("POST /auth/register", self._valid_body), None)

        assert resp["statusCode"] == 409

    def test_weak_password_returns_400(self):
        _mock_cognito.sign_up.side_effect = _client_error("InvalidPasswordException")

        resp = auth.handler(_event("POST /auth/register", {**self._valid_body, "password": "weak"}), None)

        assert resp["statusCode"] == 400

    def test_no_body_returns_400(self):
        resp = auth.handler(_event("POST /auth/register"), None)
        assert resp["statusCode"] == 400


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    _valid_body = {"email": "alice@example.com", "password": "Test123!"}
    _auth_result = {
        "AuthenticationResult": {
            "AccessToken": "access-tok",
            "IdToken": "id-tok",
            "RefreshToken": "refresh-tok",
            "ExpiresIn": 3600,
        }
    }

    def test_success_returns_200_with_tokens(self):
        _mock_cognito.initiate_auth.return_value = self._auth_result

        resp = auth.handler(_event("POST /auth/login", self._valid_body), None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["access_token"] == "access-tok"
        assert body["id_token"] == "id-tok"
        assert body["refresh_token"] == "refresh-tok"
        assert body["expires_in"] == 3600

    def test_missing_email_returns_400(self):
        resp = auth.handler(_event("POST /auth/login", {"password": "Test123!"}), None)
        assert resp["statusCode"] == 400

    def test_missing_password_returns_400(self):
        resp = auth.handler(_event("POST /auth/login", {"email": "alice@example.com"}), None)
        assert resp["statusCode"] == 400

    def test_wrong_password_returns_401(self):
        _mock_cognito.initiate_auth.side_effect = _client_error("NotAuthorizedException")

        resp = auth.handler(_event("POST /auth/login", {**self._valid_body, "password": "wrong"}), None)

        assert resp["statusCode"] == 401

    def test_nonexistent_user_returns_401(self):
        _mock_cognito.initiate_auth.side_effect = _client_error("UserNotFoundException")

        resp = auth.handler(_event("POST /auth/login", {**self._valid_body, "email": "ghost@example.com"}), None)

        assert resp["statusCode"] == 401

    def test_no_body_returns_400(self):
        resp = auth.handler(_event("POST /auth/login"), None)
        assert resp["statusCode"] == 400


# ---------------------------------------------------------------------------
# Unknown route
# ---------------------------------------------------------------------------


def test_unknown_route_returns_404():
    resp = auth.handler(_event("DELETE /auth/register"), None)
    assert resp["statusCode"] == 404
