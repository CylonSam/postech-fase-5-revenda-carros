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
os.environ["STEP_FUNCTION_ARN"] = "arn:aws:states:us-east-1:123456789:stateMachine:test-sf"

_mock_conn = MagicMock()
_mock_sf = MagicMock()
with patch("pg8000.native.Connection", return_value=_mock_conn), \
     patch("boto3.client", return_value=_mock_sf):
    _spec = importlib.util.spec_from_file_location(
        "orders_index", Path(__file__).parent / "index.py"
    )
    orders = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(orders)

_ORDER_ID = "00000000-0000-0000-0000-000000000001"
_CUSTOMER_ID = "00000000-0000-0000-0000-000000000002"
_VEHICLE_ID = "00000000-0000-0000-0000-000000000003"
_CREATED_AT = datetime(2024, 1, 1, 12, 0, 0)

_COLS = [
    {"name": "id"},
    {"name": "customer_id"},
    {"name": "vehicle_id"},
    {"name": "status"},
    {"name": "amount"},
    {"name": "created_at"},
]
_ORDER_ROW = [_ORDER_ID, _CUSTOMER_ID, _VEHICLE_ID, "pending", 5000.00, _CREATED_AT]
_CONFIRMED_ROW = [_ORDER_ID, _CUSTOMER_ID, _VEHICLE_ID, "confirmed", 5000.00, _CREATED_AT]
_ORDER_DICT = {
    "id": _ORDER_ID,
    "customerId": _CUSTOMER_ID,
    "vehicleId": _VEHICLE_ID,
    "status": "pending",
    "amount": 5000.0,
    "createdAt": _CREATED_AT.isoformat(),
}


def _event(route, path_id=None, body=None, sub=_CUSTOMER_ID, groups=None):
    claims = {"sub": sub}
    if groups is not None:
        claims["cognito:groups"] = f"[{' '.join(groups)}]"
    return {
        "routeKey": route,
        "pathParameters": {"id": path_id} if path_id else None,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"jwt": {"claims": claims}}},
    }


def _sqs_event(*records):
    return {
        "Records": [
            {"body": json.dumps(r)}
            for r in records
        ]
    }


@pytest.fixture(autouse=True)
def reset():
    _mock_conn.reset_mock()
    _mock_conn.run.side_effect = None
    _mock_conn.columns = []
    _mock_sf.reset_mock()


class TestCreateOrder:
    def test_returns_201_on_success(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(
            _event("POST /orders", body={"vehicleId": _VEHICLE_ID, "amount": 5000.0}),
            None,
        )

        assert resp["statusCode"] == 201
        assert json.loads(resp["body"]) == _ORDER_DICT

    def test_starts_step_function_with_correct_input(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        orders.handler(
            _event("POST /orders", body={"vehicleId": _VEHICLE_ID, "amount": 5000.0}),
            None,
        )

        _mock_sf.start_execution.assert_called_once()
        call_kwargs = _mock_sf.start_execution.call_args.kwargs
        assert call_kwargs["stateMachineArn"] == os.environ["STEP_FUNCTION_ARN"]
        sf_input = json.loads(call_kwargs["input"])
        assert sf_input["order"]["id"] == _ORDER_ID
        assert sf_input["order"]["vehicleId"] == _VEHICLE_ID
        assert sf_input["order"]["customerId"] == _CUSTOMER_ID
        assert sf_input["order"]["amount"] == 5000.0

    def test_missing_vehicle_id_returns_400(self):
        resp = orders.handler(_event("POST /orders", body={"amount": 5000.0}), None)

        assert resp["statusCode"] == 400
        _mock_conn.run.assert_not_called()

    def test_missing_amount_returns_400(self):
        resp = orders.handler(
            _event("POST /orders", body={"vehicleId": _VEHICLE_ID}), None
        )

        assert resp["statusCode"] == 400
        _mock_conn.run.assert_not_called()

    def test_invalid_amount_returns_400(self):
        resp = orders.handler(
            _event("POST /orders", body={"vehicleId": _VEHICLE_ID, "amount": "not-a-number"}),
            None,
        )

        assert resp["statusCode"] == 400
        _mock_conn.run.assert_not_called()

    def test_db_error_returns_500(self):
        _mock_conn.run.side_effect = orders.pg8000.native.DatabaseError(
            {"C": "XX000", "M": "internal error"}
        )

        resp = orders.handler(
            _event("POST /orders", body={"vehicleId": _VEHICLE_ID, "amount": 5000.0}),
            None,
        )

        assert resp["statusCode"] == 500


class TestListOrders:
    def test_returns_200_with_client_orders(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(_event("GET /orders"), None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body) == 1
        assert body[0]["id"] == _ORDER_ID

    def test_client_query_filters_by_customer_id(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        orders.handler(_event("GET /orders"), None)

        call_kwargs = _mock_conn.run.call_args.kwargs
        assert call_kwargs.get("customer_id") == _CUSTOMER_ID

    def test_admin_sees_all_orders_without_filter(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(_event("GET /orders", groups=["admin"]), None)

        assert resp["statusCode"] == 200
        call_kwargs = _mock_conn.run.call_args.kwargs
        assert "customer_id" not in call_kwargs

    def test_operator_sees_all_orders_without_filter(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        orders.handler(_event("GET /orders", groups=["operator"]), None)

        call_kwargs = _mock_conn.run.call_args.kwargs
        assert "customer_id" not in call_kwargs

    def test_returns_empty_list(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        resp = orders.handler(_event("GET /orders"), None)

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == []


class TestGetOrder:
    def test_returns_200_for_owner(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(_event("GET /orders/{id}", path_id=_ORDER_ID), None)

        assert resp["statusCode"] == 200
        assert json.loads(resp["body"])["id"] == _ORDER_ID

    def test_returns_403_for_different_user(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(
            _event("GET /orders/{id}", path_id=_ORDER_ID, sub="other-user-id"),
            None,
        )

        assert resp["statusCode"] == 403

    def test_admin_can_access_any_order(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(
            _event("GET /orders/{id}", path_id=_ORDER_ID, sub="other-user-id", groups=["admin"]),
            None,
        )

        assert resp["statusCode"] == 200

    def test_operator_can_access_any_order(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        resp = orders.handler(
            _event("GET /orders/{id}", path_id=_ORDER_ID, sub="other-user-id", groups=["operator"]),
            None,
        )

        assert resp["statusCode"] == 200

    def test_returns_404_when_not_found(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        resp = orders.handler(_event("GET /orders/{id}", path_id=_ORDER_ID), None)

        assert resp["statusCode"] == 404


class TestValidateOrder:
    def _sf_event(self, order_id=_ORDER_ID):
        return {
            "action": "validateOrder",
            "order": {
                "id": order_id,
                "vehicleId": _VEHICLE_ID,
                "customerId": _CUSTOMER_ID,
                "amount": 5000.0,
            },
        }

    def test_returns_order_dict_when_found(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        result = orders.handler(self._sf_event(), None)

        assert result["id"] == _ORDER_ID
        assert result["status"] == "pending"

    def test_raises_when_not_found(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        with pytest.raises(ValueError):
            orders.handler(self._sf_event(), None)

    def test_passes_order_id_to_query(self):
        _mock_conn.run.return_value = [_ORDER_ROW]
        _mock_conn.columns = _COLS

        orders.handler(self._sf_event(), None)

        call_kwargs = _mock_conn.run.call_args.kwargs
        assert call_kwargs.get("id") == _ORDER_ID


class TestConfirmOrder:
    def _sf_event(self, order_id=_ORDER_ID):
        return {
            "action": "confirmOrder",
            "orderId": order_id,
            "payment": {"paymentId": "pay-123", "status": "success"},
        }

    def test_returns_confirmed_order(self):
        _mock_conn.run.return_value = [_CONFIRMED_ROW]
        _mock_conn.columns = _COLS

        result = orders.handler(self._sf_event(), None)

        assert result["id"] == _ORDER_ID
        assert result["status"] == "confirmed"

    def test_raises_when_not_found(self):
        _mock_conn.run.return_value = []
        _mock_conn.columns = _COLS

        with pytest.raises(ValueError):
            orders.handler(self._sf_event(), None)

    def test_passes_order_id_to_query(self):
        _mock_conn.run.return_value = [_CONFIRMED_ROW]
        _mock_conn.columns = _COLS

        orders.handler(self._sf_event(), None)

        call_kwargs = _mock_conn.run.call_args.kwargs
        assert call_kwargs.get("id") == _ORDER_ID


class TestRefundPayment:
    def _sf_event(self, order_id=_ORDER_ID):
        return {
            "action": "refundPayment",
            "orderId": order_id,
            "payment": {"paymentId": "pay-123"},
        }

    def test_returns_refund_dict(self):
        _mock_conn.run.return_value = []

        result = orders.handler(self._sf_event(), None)

        assert result["orderId"] == _ORDER_ID
        assert result["status"] == "refunded"

    def test_passes_order_id_to_query(self):
        _mock_conn.run.return_value = []

        orders.handler(self._sf_event(), None)

        call_kwargs = _mock_conn.run.call_args.kwargs
        assert call_kwargs.get("id") == _ORDER_ID


class TestSqsHandler:
    def test_sends_task_success_with_task_token(self):
        orders.handler(
            _sqs_event({"taskToken": "token-123", "orderId": _ORDER_ID, "amount": 5000.0, "customerId": _CUSTOMER_ID}),
            None,
        )

        _mock_sf.send_task_success.assert_called_once()
        call_kwargs = _mock_sf.send_task_success.call_args.kwargs
        assert call_kwargs["taskToken"] == "token-123"

    def test_payment_output_contains_payment_id_and_success_status(self):
        orders.handler(
            _sqs_event({"taskToken": "token-123", "orderId": _ORDER_ID, "amount": 5000.0, "customerId": _CUSTOMER_ID}),
            None,
        )

        call_kwargs = _mock_sf.send_task_success.call_args.kwargs
        output = json.loads(call_kwargs["output"])
        assert output["status"] == "success"
        assert "paymentId" in output

    def test_handles_multiple_records(self):
        orders.handler(
            _sqs_event(
                {"taskToken": "token-1", "orderId": _ORDER_ID, "amount": 1000.0, "customerId": _CUSTOMER_ID},
                {"taskToken": "token-2", "orderId": _ORDER_ID, "amount": 2000.0, "customerId": _CUSTOMER_ID},
            ),
            None,
        )

        assert _mock_sf.send_task_success.call_count == 2

    def test_payment_id_is_unique_per_record(self):
        orders.handler(
            _sqs_event(
                {"taskToken": "token-1", "orderId": _ORDER_ID, "amount": 1000.0, "customerId": _CUSTOMER_ID},
                {"taskToken": "token-2", "orderId": _ORDER_ID, "amount": 2000.0, "customerId": _CUSTOMER_ID},
            ),
            None,
        )

        calls = _mock_sf.send_task_success.call_args_list
        payment_ids = [json.loads(c.kwargs["output"])["paymentId"] for c in calls]
        assert payment_ids[0] != payment_ids[1]


def test_unknown_route_returns_404():
    resp = orders.handler(_event("DELETE /orders"), None)
    assert resp["statusCode"] == 404


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        orders.handler({"action": "unknownAction"}, None)
