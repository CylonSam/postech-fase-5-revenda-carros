import json
import os
import uuid

import boto3
import pg8000.native

DB_ENDPOINT = os.environ["DB_ENDPOINT"]
DB_NAME = os.environ["DB_NAME"]
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USERNAME = os.environ["DB_USERNAME"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
STEP_FUNCTION_ARN = os.environ["STEP_FUNCTION_ARN"]

_conn = pg8000.native.Connection(
    host=DB_ENDPOINT,
    database=DB_NAME,
    user=DB_USERNAME,
    password=DB_PASSWORD,
    port=DB_PORT,
)

_sf_client = boto3.client("stepfunctions")

_conn.run(
    """
    CREATE TABLE IF NOT EXISTS orders (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        customer_id UUID NOT NULL,
        vehicle_id  UUID NOT NULL,
        status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'confirmed', 'failed', 'refunded')),
        amount      NUMERIC(12,2) NOT NULL,
        created_at  TIMESTAMP DEFAULT NOW(),
        updated_at  TIMESTAMP DEFAULT NOW()
    )
    """
)

_conn.run(
    """
    CREATE TABLE IF NOT EXISTS payments (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        payment_code UUID NOT NULL UNIQUE,
        order_id     UUID NOT NULL,
        task_token   TEXT NOT NULL,
        status       VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'success')),
        created_at   TIMESTAMP DEFAULT NOW()
    )
    """
)

_ADMIN_ROLES = {"admin", "operator"}
_SELECT = "SELECT id, customer_id, vehicle_id, status, amount, created_at FROM orders"


def _groups(event):
    raw = event["requestContext"]["authorizer"]["jwt"]["claims"].get("cognito:groups", "")
    if not raw:
        return set()
    return set(raw.strip("[]").split())


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _row_to_dict(cols, row):
    d = dict(zip(cols, row))
    return {
        "id": str(d["id"]),
        "customerId": str(d["customer_id"]),
        "vehicleId": str(d["vehicle_id"]),
        "status": d["status"],
        "amount": float(d["amount"]),
        "createdAt": d["created_at"].isoformat() if d["created_at"] else None,
    }


def _create_order(event):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    customer_id = claims.get("sub", "")
    body = json.loads(event.get("body") or "{}")
    vehicle_id = body.get("vehicleId", "")
    amount = body.get("amount")
    if not vehicle_id:
        return _response(400, {"error": "vehicleId is required"})
    if amount is None:
        return _response(400, {"error": "amount is required"})
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return _response(400, {"error": "amount must be a number"})
    try:
        rows = _conn.run(
            "INSERT INTO orders (customer_id, vehicle_id, amount) "
            "VALUES (:customer_id::UUID, :vehicle_id::UUID, :amount) "
            "RETURNING id, customer_id, vehicle_id, status, amount, created_at",
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            amount=amount,
        )
        cols = [c["name"] for c in _conn.columns]
        order = _row_to_dict(cols, rows[0])
        _sf_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            input=json.dumps({
                "order": {
                    "id": order["id"],
                    "customerId": order["customerId"],
                    "vehicleId": order["vehicleId"],
                    "amount": order["amount"],
                }
            }),
        )
        return _response(201, order)
    except pg8000.native.DatabaseError:
        return _response(500, {"error": "Could not create order"})


def _list_orders(event):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    customer_id = claims.get("sub", "")
    if _groups(event) & _ADMIN_ROLES:
        rows = _conn.run(f"{_SELECT} ORDER BY created_at DESC")
    else:
        rows = _conn.run(
            f"{_SELECT} WHERE customer_id = :customer_id::UUID ORDER BY created_at DESC",
            customer_id=customer_id,
        )
    cols = [c["name"] for c in _conn.columns]
    return _response(200, [_row_to_dict(cols, row) for row in rows])


def _get_order(event):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    customer_id = claims.get("sub", "")
    order_id = (event.get("pathParameters") or {}).get("id", "")
    rows = _conn.run(f"{_SELECT} WHERE id = :id::UUID", id=order_id)
    cols = [c["name"] for c in _conn.columns]
    if not rows:
        return _response(404, {"error": "Order not found"})
    order = _row_to_dict(cols, rows[0])
    if order["customerId"] != customer_id and not (_groups(event) & _ADMIN_ROLES):
        return _response(403, {"error": "Access denied"})
    return _response(200, order)


def _get_order_payment(event):
    order_id = (event.get("pathParameters") or {}).get("id", "")
    rows = _conn.run(
        "SELECT payment_code, status FROM payments "
        "WHERE order_id = :order_id::UUID ORDER BY created_at DESC LIMIT 1",
        order_id=order_id,
    )
    cols = [c["name"] for c in _conn.columns]
    if not rows:
        return _response(404, {"error": "No payment found for this order"})
    p = dict(zip(cols, rows[0]))
    return _response(200, {"paymentCode": str(p["payment_code"]), "status": p["status"]})


def _validate_order(event):
    order = event.get("order", {})
    order_id = order.get("id", "")
    rows = _conn.run(f"{_SELECT} WHERE id = :id::UUID", id=order_id)
    cols = [c["name"] for c in _conn.columns]
    if not rows:
        raise ValueError(f"Order {order_id} not found")
    return _row_to_dict(cols, rows[0])


def _confirm_order(event):
    order_id = event.get("orderId", "")
    rows = _conn.run(
        "UPDATE orders SET status = 'confirmed', updated_at = NOW() "
        "WHERE id = :id::UUID "
        "RETURNING id, customer_id, vehicle_id, status, amount, created_at",
        id=order_id,
    )
    cols = [c["name"] for c in _conn.columns]
    if not rows:
        raise ValueError(f"Order {order_id} not found")
    return _row_to_dict(cols, rows[0])


def _refund_payment(event):
    order_id = event.get("orderId", "")
    _conn.run(
        "UPDATE orders SET status = 'refunded', updated_at = NOW() "
        "WHERE id = :id::UUID",
        id=order_id,
    )
    return {"orderId": order_id, "status": "refunded"}


def _handle_sqs(event):
    for record in event["Records"]:
        body = json.loads(record["body"])
        payment_code = str(uuid.uuid4())
        _conn.run(
            "INSERT INTO payments (payment_code, order_id, task_token) "
            "VALUES (:payment_code::UUID, :order_id::UUID, :task_token)",
            payment_code=payment_code,
            order_id=body["orderId"],
            task_token=body["taskToken"],
        )


def _confirm_payment(event):
    body = json.loads(event.get("body") or "{}")
    payment_code = body.get("paymentCode", "")
    if not payment_code:
        return _response(400, {"error": "paymentCode is required"})

    rows = _conn.run(
        "SELECT id, task_token, order_id, status FROM payments WHERE payment_code = :code::UUID",
        code=payment_code,
    )
    cols = [c["name"] for c in _conn.columns]
    if not rows:
        return _response(404, {"error": "Payment not found"})

    payment = dict(zip(cols, rows[0]))
    if payment["status"] != "pending":
        return _response(409, {"error": "Payment already processed"})

    payment_id = str(uuid.uuid4())
    _sf_client.send_task_success(
        taskToken=payment["task_token"],
        output=json.dumps({"paymentId": payment_id, "status": "success"}),
    )
    _conn.run(
        "UPDATE payments SET status = 'success' WHERE payment_code = :code::UUID",
        code=payment_code,
    )
    return _response(200, {"paymentId": payment_id, "orderId": str(payment["order_id"]), "status": "success"})


def handler(event, context):
    if "Records" in event:
        _handle_sqs(event)
        return

    action = event.get("action")
    if action:
        if action == "validateOrder":
            return _validate_order(event)
        if action == "confirmOrder":
            return _confirm_order(event)
        if action == "refundPayment":
            return _refund_payment(event)
        raise ValueError(f"Unknown action: {action}")

    route = event.get("routeKey", "")
    if route == "POST /orders":
        return _create_order(event)
    if route == "GET /orders":
        return _list_orders(event)
    if route == "GET /orders/{id}":
        return _get_order(event)
    if route == "GET /orders/{id}/payment":
        return _get_order_payment(event)
    if route == "POST /payments/webhook":
        return _confirm_payment(event)

    return _response(404, {"error": "Route not found"})
