import importlib.util
import json
import os
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
    _spec = importlib.util.spec_from_file_location(
        "vehicles_index", Path(__file__).parent / "index.py"
    )
    vehicles = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(vehicles)

_VEHICLE_ID = "00000000-0000-0000-0000-000000000001"
_COLS = [
    {"name": "id"},
    {"name": "brand"},
    {"name": "model"},
    {"name": "year"},
    {"name": "color"},
    {"name": "price"},
    {"name": "plate"},
]
_VEHICLE_ROW = [_VEHICLE_ID, "Toyota", "Corolla", 2022, "Blue", 25000.00, "ABC-1234"]
_VEHICLE_DICT = {
    "id": _VEHICLE_ID,
    "brand": "Toyota",
    "model": "Corolla",
    "year": 2022,
    "color": "Blue",
    "price": 25000.0,
    "plate": "ABC-1234",
}
_VALID_BODY = {
    "brand": "Toyota",
    "model": "Corolla",
    "year": 2022,
    "color": "Blue",
    "price": 25000.00,
    "plate": "ABC-1234",
}


def _event(route, path_id=None, body=None, groups=None):
    event = {
        "routeKey": route,
        "pathParameters": {"id": path_id} if path_id else None,
        "body": json.dumps(body) if body is not None else None,
    }
    if groups is not None:
        event["requestContext"] = {
            "authorizer": {
                "jwt": {"claims": {"cognito:groups": " ".join(groups)}}
            }
        }
    return event


@pytest.fixture(autouse=True)
def reset():
    _mock_conn.reset_mock()
    _mock_conn.run.side_effect = None
    _mock_conn.columns = []


class TestListVehicles:
    def test_returns_200_with_empty_list(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        resp = vehicles.handler(_event("GET /vehicles"), None)

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == []

    def test_returns_200_with_vehicles(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        resp = vehicles.handler(_event("GET /vehicles"), None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body == [_VEHICLE_DICT]


class TestGetVehicle:
    def test_returns_200_when_found(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        resp = vehicles.handler(_event("GET /vehicles/{id}", path_id=_VEHICLE_ID), None)

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == _VEHICLE_DICT

    def test_returns_404_when_not_found(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        resp = vehicles.handler(_event("GET /vehicles/{id}", path_id=_VEHICLE_ID), None)

        assert resp["statusCode"] == 404

    def test_passes_id_to_query(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        vehicles.handler(_event("GET /vehicles/{id}", path_id=_VEHICLE_ID), None)

        call_kwargs = _mock_conn.run.call_args
        assert call_kwargs.kwargs.get("id") == _VEHICLE_ID


class TestCreateVehicle:
    def test_returns_201_as_admin(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        resp = vehicles.handler(
            _event("POST /vehicles", body=_VALID_BODY, groups=["admin"]), None
        )

        assert resp["statusCode"] == 201
        assert json.loads(resp["body"]) == _VEHICLE_DICT

    def test_returns_201_as_operator(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        resp = vehicles.handler(
            _event("POST /vehicles", body=_VALID_BODY, groups=["operator"]), None
        )

        assert resp["statusCode"] == 201

    def test_returns_403_as_client(self):
        resp = vehicles.handler(
            _event("POST /vehicles", body=_VALID_BODY, groups=["client"]), None
        )
        assert resp["statusCode"] == 403
        _mock_conn.run.assert_not_called()

    def test_returns_403_with_no_group(self):
        resp = vehicles.handler(
            _event("POST /vehicles", body=_VALID_BODY, groups=[]), None
        )
        assert resp["statusCode"] == 403
        _mock_conn.run.assert_not_called()

    def test_missing_field_returns_400(self):
        for field in ("brand", "model", "year", "color", "price", "plate"):
            body = {k: v for k, v in _VALID_BODY.items() if k != field}
            resp = vehicles.handler(
                _event("POST /vehicles", body=body, groups=["operator"]), None
            )
            assert resp["statusCode"] == 400, f"expected 400 when {field} is missing"
        _mock_conn.run.assert_not_called()

    def test_invalid_year_returns_400(self):
        body = {**_VALID_BODY, "year": "not-a-year"}
        resp = vehicles.handler(
            _event("POST /vehicles", body=body, groups=["operator"]), None
        )
        assert resp["statusCode"] == 400

    def test_invalid_price_returns_400(self):
        body = {**_VALID_BODY, "price": "not-a-price"}
        resp = vehicles.handler(
            _event("POST /vehicles", body=body, groups=["operator"]), None
        )
        assert resp["statusCode"] == 400

    def test_duplicate_plate_returns_409(self):
        _mock_conn.run.side_effect = vehicles.pg8000.native.DatabaseError(
            {"C": "23505", "M": "duplicate key value violates unique constraint"}
        )

        resp = vehicles.handler(
            _event("POST /vehicles", body=_VALID_BODY, groups=["operator"]), None
        )

        assert resp["statusCode"] == 409

    def test_db_error_returns_500(self):
        _mock_conn.run.side_effect = vehicles.pg8000.native.DatabaseError(
            {"C": "XX000", "M": "internal error"}
        )

        resp = vehicles.handler(
            _event("POST /vehicles", body=_VALID_BODY, groups=["admin"]), None
        )

        assert resp["statusCode"] == 500

    def test_no_body_returns_400(self):
        resp = vehicles.handler(
            _event("POST /vehicles", groups=["operator"]), None
        )
        assert resp["statusCode"] == 400


class TestUpdateVehicle:
    def test_returns_200_as_admin(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        resp = vehicles.handler(
            _event("PUT /vehicles/{id}", path_id=_VEHICLE_ID, body=_VALID_BODY, groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == _VEHICLE_DICT

    def test_returns_200_as_operator(self):
        _mock_conn.run.return_value = [_VEHICLE_ROW]
        _mock_conn.columns = _COLS

        resp = vehicles.handler(
            _event("PUT /vehicles/{id}", path_id=_VEHICLE_ID, body=_VALID_BODY, groups=["operator"]),
            None,
        )

        assert resp["statusCode"] == 200

    def test_returns_403_as_client(self):
        resp = vehicles.handler(
            _event("PUT /vehicles/{id}", path_id=_VEHICLE_ID, body=_VALID_BODY, groups=["client"]),
            None,
        )
        assert resp["statusCode"] == 403
        _mock_conn.run.assert_not_called()

    def test_returns_404_when_not_found(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        resp = vehicles.handler(
            _event("PUT /vehicles/{id}", path_id=_VEHICLE_ID, body=_VALID_BODY, groups=["operator"]),
            None,
        )

        assert resp["statusCode"] == 404

    def test_missing_field_returns_400(self):
        body = {k: v for k, v in _VALID_BODY.items() if k != "brand"}
        resp = vehicles.handler(
            _event("PUT /vehicles/{id}", path_id=_VEHICLE_ID, body=body, groups=["operator"]),
            None,
        )
        assert resp["statusCode"] == 400

    def test_duplicate_plate_returns_409(self):
        _mock_conn.run.side_effect = vehicles.pg8000.native.DatabaseError(
            {"C": "23505", "M": "duplicate key value violates unique constraint"}
        )

        resp = vehicles.handler(
            _event("PUT /vehicles/{id}", path_id=_VEHICLE_ID, body=_VALID_BODY, groups=["operator"]),
            None,
        )

        assert resp["statusCode"] == 409


def test_unknown_route_returns_404():
    resp = vehicles.handler(_event("DELETE /vehicles/{id}"), None)
    assert resp["statusCode"] == 404
