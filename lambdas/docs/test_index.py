import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ["DB_ENDPOINT"] = "localhost"
os.environ["DB_NAME"] = "testdb"
os.environ["DB_PORT"] = "5432"
os.environ["DB_USERNAME"] = "test"
os.environ["DB_PASSWORD"] = "test"

_mock_conn = MagicMock()
with patch("pg8000.native.Connection", return_value=_mock_conn):
    _spec = importlib.util.spec_from_file_location("docs", Path(__file__).parent / "index.py")
    docs = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(docs)

_ORDER_ID = "00000000-0000-0000-0000-000000000001"
_CUSTOMER_ID = "00000000-0000-0000-0000-000000000002"
_PAYMENT_CODE = "00000000-0000-0000-0000-000000000003"
_CREATED_AT = datetime(2024, 1, 1, 12, 0, 0)

_DOC_COLS = [
    {"name": "id"},
    {"name": "customer_id"},
    {"name": "status"},
    {"name": "amount"},
    {"name": "created_at"},
    {"name": "retriever_license"},
    {"name": "retriever_tax_id"},
    {"name": "brand"},
    {"name": "model"},
    {"name": "year"},
    {"name": "color"},
    {"name": "plate"},
    {"name": "price"},
    {"name": "payment_code"},
    {"name": "payment_status"},
]

_DOC_ROW = [
    _ORDER_ID, _CUSTOMER_ID, "confirmed", 50000.00, _CREATED_AT,
    "CNH-123456", "123.456.789-00",
    "Toyota", "Corolla", 2022, "Blue", "ABC-1234", 50000.00,
    _PAYMENT_CODE, "success",
]

_DOC_ROW_NO_PAYMENT = [
    _ORDER_ID, _CUSTOMER_ID, "pending", 50000.00, _CREATED_AT,
    None, None,
    "Toyota", "Corolla", 2022, "Blue", "ABC-1234", 50000.00,
    None, None,
]


def _event(route, path_params=None, sub=_CUSTOMER_ID, groups=None):
    claims = {"sub": sub}
    if groups is not None:
        claims["cognito:groups"] = f"[{' '.join(groups)}]"
    return {
        "routeKey": route,
        "pathParameters": path_params,
        "requestContext": {"authorizer": {"jwt": {"claims": claims}}},
    }


@pytest.fixture(autouse=True)
def reset():
    _mock_conn.reset_mock()
    _mock_conn.run.side_effect = None
    _mock_conn.columns = _DOC_COLS


class TestGetDoc:
    def test_customer_gets_own_order_returns_200(self):
        _mock_conn.run.return_value = [_DOC_ROW]

        resp = docs.handler(
            _event("GET /docs/{orderId}", path_params={"orderId": _ORDER_ID}),
            None,
        )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["orderId"] == _ORDER_ID
        assert body["customerId"] == _CUSTOMER_ID

    def test_admin_gets_any_order_returns_200(self):
        _mock_conn.run.return_value = [_DOC_ROW]

        resp = docs.handler(
            _event(
                "GET /docs/{orderId}",
                path_params={"orderId": _ORDER_ID},
                sub="other-user-id",
                groups=["admin"],
            ),
            None,
        )

        assert resp["statusCode"] == 200

    def test_operator_gets_any_order_returns_200(self):
        _mock_conn.run.return_value = [_DOC_ROW]

        resp = docs.handler(
            _event(
                "GET /docs/{orderId}",
                path_params={"orderId": _ORDER_ID},
                sub="other-user-id",
                groups=["operator"],
            ),
            None,
        )

        assert resp["statusCode"] == 200

    def test_customer_accessing_another_order_returns_403(self):
        _mock_conn.run.return_value = [_DOC_ROW]

        resp = docs.handler(
            _event(
                "GET /docs/{orderId}",
                path_params={"orderId": _ORDER_ID},
                sub="other-user-id",
            ),
            None,
        )

        assert resp["statusCode"] == 403

    def test_order_not_found_returns_404(self):
        _mock_conn.run.return_value = []

        resp = docs.handler(
            _event("GET /docs/{orderId}", path_params={"orderId": _ORDER_ID}),
            None,
        )

        assert resp["statusCode"] == 404

    def test_db_error_returns_500(self):
        _mock_conn.run.side_effect = docs.pg8000.native.DatabaseError

        resp = docs.handler(
            _event("GET /docs/{orderId}", path_params={"orderId": _ORDER_ID}),
            None,
        )

        assert resp["statusCode"] == 500

    def test_response_body_has_payment_and_retriever(self):
        _mock_conn.run.return_value = [_DOC_ROW]

        resp = docs.handler(
            _event("GET /docs/{orderId}", path_params={"orderId": _ORDER_ID}),
            None,
        )

        body = json.loads(resp["body"])
        assert set(body.keys()) == {
            "orderId", "status", "createdAt", "customerId", "vehicle", "retriever", "payment",
        }
        assert set(body["vehicle"].keys()) == {"brand", "model", "year", "color", "plate", "price"}
        assert body["retriever"] == {"license": "CNH-123456", "taxId": "123.456.789-00"}
        assert body["payment"] == {"code": _PAYMENT_CODE, "status": "success"}

    def test_payment_is_none_when_no_payment(self):
        _mock_conn.run.return_value = [_DOC_ROW_NO_PAYMENT]

        resp = docs.handler(
            _event("GET /docs/{orderId}", path_params={"orderId": _ORDER_ID}),
            None,
        )

        body = json.loads(resp["body"])
        assert body["payment"] is None

    def test_retriever_is_none_when_no_retriever(self):
        _mock_conn.run.return_value = [_DOC_ROW_NO_PAYMENT]

        resp = docs.handler(
            _event("GET /docs/{orderId}", path_params={"orderId": _ORDER_ID}),
            None,
        )

        body = json.loads(resp["body"])
        assert body["retriever"] is None


def test_unknown_route_returns_404():
    resp = docs.handler(_event("POST /docs"), None)
    assert resp["statusCode"] == 404
