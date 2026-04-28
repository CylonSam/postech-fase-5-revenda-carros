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
    _spec = importlib.util.spec_from_file_location(
        "stock_index", Path(__file__).parent / "index.py"
    )
    stock = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(stock)

_VEHICLE_ID = "00000000-0000-0000-0000-000000000001"
_ORDER_ID = "00000000-0000-0000-0000-000000000002"
_UPDATED_AT = datetime(2024, 1, 1, 12, 0, 0)

_COLS = [
    {"name": "vehicle_id"},
    {"name": "status"},
    {"name": "order_id"},
    {"name": "updated_at"},
]
_AVAILABLE_ROW = [_VEHICLE_ID, "available", None, _UPDATED_AT]
_RESERVED_ROW = [_VEHICLE_ID, "reserved", _ORDER_ID, _UPDATED_AT]
_SOLD_ROW = [_VEHICLE_ID, "sold", None, _UPDATED_AT]

_AVAILABLE_DICT = {
    "vehicleId": _VEHICLE_ID,
    "status": "available",
    "orderId": None,
    "updatedAt": _UPDATED_AT.isoformat(),
}


def _event(route, vehicle_id=None, body=None, groups=None):
    event = {
        "routeKey": route,
        "pathParameters": {"vehicleId": vehicle_id} if vehicle_id else None,
        "body": json.dumps(body) if body is not None else None,
    }
    if groups is not None:
        event["requestContext"] = {
            "authorizer": {
                "jwt": {"claims": {"cognito:groups": f"[{' '.join(groups)}]"}}
            }
        }
    return event


@pytest.fixture(autouse=True)
def reset():
    _mock_conn.reset_mock()
    _mock_conn.run.side_effect = None
    _mock_conn.columns = []


class TestListStock:
    def test_returns_200_with_empty_list(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        resp = stock.handler(_event("GET /stock"), None)

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == []

    def test_returns_200_with_stock_records(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        resp = stock.handler(_event("GET /stock"), None)

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == [_AVAILABLE_DICT]


class TestUpdateStock:
    def test_returns_200_as_admin(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "available"}, groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == _AVAILABLE_DICT

    def test_returns_200_as_operator(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "available"}, groups=["operator"]),
            None,
        )

        assert resp["statusCode"] == 200

    def test_returns_200_with_sold_status(self):
        _mock_conn.run.return_value = [_SOLD_ROW]
        _mock_conn.columns = _COLS

        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "sold"}, groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "sold"

    def test_returns_403_as_client(self):
        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "available"}, groups=["client"]),
            None,
        )

        assert resp["statusCode"] == 403
        _mock_conn.run.assert_not_called()

    def test_returns_403_with_no_group(self):
        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "available"}, groups=[]),
            None,
        )

        assert resp["statusCode"] == 403
        _mock_conn.run.assert_not_called()

    def test_missing_status_returns_400(self):
        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={}, groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 400
        _mock_conn.run.assert_not_called()

    def test_invalid_status_returns_400(self):
        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "reserved"}, groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 400
        _mock_conn.run.assert_not_called()

    def test_db_error_returns_500(self):
        _mock_conn.run.side_effect = stock.pg8000.native.DatabaseError(
            {"C": "XX000", "M": "internal error"}
        )

        resp = stock.handler(
            _event("PUT /stock/{vehicleId}", vehicle_id=_VEHICLE_ID, body={"status": "available"}, groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 500


class TestCheckStock:
    def _sf_event(self, vehicle_id=_VEHICLE_ID):
        return {"action": "checkStock", "vehicleId": vehicle_id}

    def test_returns_dict_when_available(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        result = stock.handler(self._sf_event(), None)

        assert result["vehicleId"] == _VEHICLE_ID
        assert result["status"] == "available"

    def test_raises_when_reserved(self):
        _mock_conn.run.return_value = [_RESERVED_ROW]
        _mock_conn.columns = _COLS

        with pytest.raises(stock.StockUnavailableError):
            stock.handler(self._sf_event(), None)

    def test_raises_when_sold(self):
        _mock_conn.run.return_value = [_SOLD_ROW]
        _mock_conn.columns = _COLS

        with pytest.raises(stock.StockUnavailableError):
            stock.handler(self._sf_event(), None)

    def test_raises_when_not_found(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        with pytest.raises(stock.StockUnavailableError):
            stock.handler(self._sf_event(), None)

    def test_passes_vehicle_id_to_query(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        stock.handler(self._sf_event(), None)

        call_kwargs = _mock_conn.run.call_args
        assert call_kwargs.kwargs.get("vehicle_id") == _VEHICLE_ID


class TestReserveStock:
    def _sf_event(self, vehicle_id=_VEHICLE_ID, order_id=_ORDER_ID):
        return {"action": "reserveStock", "vehicleId": vehicle_id, "orderId": order_id}

    def test_returns_dict_on_success(self):
        _mock_conn.run.return_value = [_RESERVED_ROW]
        _mock_conn.columns = _COLS

        result = stock.handler(self._sf_event(), None)

        assert result["vehicleId"] == _VEHICLE_ID
        assert result["status"] == "reserved"

    def test_raises_when_no_rows_affected(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        with pytest.raises(stock.StockUnavailableError):
            stock.handler(self._sf_event(), None)

    def test_passes_vehicle_id_and_order_id_to_query(self):
        _mock_conn.run.return_value = [_RESERVED_ROW]
        _mock_conn.columns = _COLS

        stock.handler(self._sf_event(), None)

        call_kwargs = _mock_conn.run.call_args
        assert call_kwargs.kwargs.get("vehicle_id") == _VEHICLE_ID
        assert call_kwargs.kwargs.get("order_id") == _ORDER_ID


class TestReleaseStock:
    def _sf_event(self, vehicle_id=_VEHICLE_ID, order_id=_ORDER_ID):
        return {"action": "releaseStock", "vehicleId": vehicle_id, "orderId": order_id}

    def test_returns_dict_when_released(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        result = stock.handler(self._sf_event(), None)

        assert result["vehicleId"] == _VEHICLE_ID
        assert result["status"] == "available"

    def test_idempotent_when_no_rows_affected(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        result = stock.handler(self._sf_event(), None)

        assert result["vehicleId"] == _VEHICLE_ID
        assert result["status"] == "available"

    def test_passes_vehicle_id_and_order_id_to_query(self):
        _mock_conn.run.return_value = [_AVAILABLE_ROW]
        _mock_conn.columns = _COLS

        stock.handler(self._sf_event(), None)

        call_kwargs = _mock_conn.run.call_args
        assert call_kwargs.kwargs.get("vehicle_id") == _VEHICLE_ID
        assert call_kwargs.kwargs.get("order_id") == _ORDER_ID


def test_unknown_route_returns_404():
    resp = stock.handler(_event("DELETE /stock"), None)
    assert resp["statusCode"] == 404


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        stock.handler({"action": "unknownAction"}, None)
