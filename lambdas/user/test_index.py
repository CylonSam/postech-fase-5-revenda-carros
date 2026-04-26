import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Set env vars before the module is loaded
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_testpool"
os.environ["COGNITO_CLIENT_ID"] = "test_client_id"

# Load the lambda module with a mocked boto3 client
_mock_cognito = MagicMock()
with patch("boto3.client", return_value=_mock_cognito):
    _spec = importlib.util.spec_from_file_location("user_index", Path(__file__).parent / "index.py")
    user = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(user)

_SUB = "user-sub-abc-123"
_EMAIL = "alice@example.com"


def _event(route, path_id=_SUB, body=None, sub=_SUB, email=_EMAIL):
    return {
        "routeKey": route,
        "pathParameters": {"id": path_id},
        "body": json.dumps(body) if body else None,
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {"sub": sub, "email": email}
                }
            }
        },
    }


@pytest.fixture(autouse=True)
def reset():
    _mock_cognito.reset_mock()


# ---------------------------------------------------------------------------
# GET /users/{id}
# ---------------------------------------------------------------------------


class TestGetUser:
    def test_success_returns_200_with_profile(self):
        _mock_cognito.admin_get_user.return_value = {
            "UserAttributes": [
                {"Name": "sub", "Value": _SUB},
                {"Name": "email", "Value": _EMAIL},
                {"Name": "name", "Value": "Alice"},
            ]
        }

        resp = user.handler(_event("GET /users/{id}"), None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["sub"] == _SUB
        assert body["email"] == _EMAIL
        assert body["name"] == "Alice"
        _mock_cognito.admin_get_user.assert_called_once_with(
            UserPoolId="us-east-1_testpool", Username=_EMAIL
        )

    def test_forbidden_when_path_id_differs_from_token_sub(self):
        resp = user.handler(_event("GET /users/{id}", path_id="someone-elses-sub"), None)
        assert resp["statusCode"] == 403
        _mock_cognito.admin_get_user.assert_not_called()

    def test_cognito_error_returns_500(self):
        from botocore.exceptions import ClientError

        _mock_cognito.admin_get_user.side_effect = ClientError(
            {"Error": {"Code": "InternalErrorException", "Message": "fail"}}, "op"
        )

        resp = user.handler(_event("GET /users/{id}"), None)

        assert resp["statusCode"] == 500


# ---------------------------------------------------------------------------
# PUT /users/{id}
# ---------------------------------------------------------------------------


class TestUpdateUser:
    def test_success_returns_200(self):
        _mock_cognito.admin_update_user_attributes.return_value = {}

        resp = user.handler(_event("PUT /users/{id}", body={"name": "Bob"}), None)

        assert resp["statusCode"] == 200
        _mock_cognito.admin_update_user_attributes.assert_called_once_with(
            UserPoolId="us-east-1_testpool",
            Username=_EMAIL,
            UserAttributes=[{"Name": "name", "Value": "Bob"}],
        )

    def test_missing_name_returns_400(self):
        resp = user.handler(_event("PUT /users/{id}", body={}), None)
        assert resp["statusCode"] == 400
        _mock_cognito.admin_update_user_attributes.assert_not_called()

    def test_blank_name_returns_400(self):
        resp = user.handler(_event("PUT /users/{id}", body={"name": "   "}), None)
        assert resp["statusCode"] == 400

    def test_forbidden_when_path_id_differs_from_token_sub(self):
        resp = user.handler(_event("PUT /users/{id}", path_id="someone-elses-sub", body={"name": "Bob"}), None)
        assert resp["statusCode"] == 403
        _mock_cognito.admin_update_user_attributes.assert_not_called()

    def test_no_body_returns_400(self):
        resp = user.handler(_event("PUT /users/{id}"), None)
        assert resp["statusCode"] == 400

    def test_cognito_error_returns_500(self):
        from botocore.exceptions import ClientError

        _mock_cognito.admin_update_user_attributes.side_effect = ClientError(
            {"Error": {"Code": "InternalErrorException", "Message": "fail"}}, "op"
        )

        resp = user.handler(_event("PUT /users/{id}", body={"name": "Bob"}), None)

        assert resp["statusCode"] == 500


# ---------------------------------------------------------------------------
# Unknown route
# ---------------------------------------------------------------------------


def test_unknown_route_returns_404():
    resp = user.handler(_event("DELETE /users/{id}"), None)
    assert resp["statusCode"] == 404
