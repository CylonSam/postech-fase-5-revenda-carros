import json
import os

import pg8000.native

DB_ENDPOINT = os.environ["DB_ENDPOINT"]
DB_NAME = os.environ["DB_NAME"]
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USERNAME = os.environ["DB_USERNAME"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

_conn = pg8000.native.Connection(
    host=DB_ENDPOINT,
    database=DB_NAME,
    user=DB_USERNAME,
    password=DB_PASSWORD,
    port=DB_PORT,
)

_conn.run(
    """
    CREATE TABLE IF NOT EXISTS stock (
        vehicle_id UUID PRIMARY KEY,
        status     VARCHAR(20) NOT NULL DEFAULT 'available'
                       CHECK (status IN ('available', 'reserved', 'sold')),
        order_id   UUID,
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """
)

_WRITE_ROLES = {"admin", "operator"}
_VALID_STATUSES = {"available", "sold"}

_SELECT = "SELECT vehicle_id, status, order_id, updated_at FROM stock"


class StockUnavailableError(Exception):
    pass


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
        "vehicleId": str(d["vehicle_id"]),
        "status": d["status"],
        "orderId": str(d["order_id"]) if d["order_id"] else None,
        "updatedAt": d["updated_at"].isoformat() if d["updated_at"] else None,
    }


def _list_stock(event):
    rows = _conn.run(f"{_SELECT} ORDER BY updated_at DESC")
    cols = [c["name"] for c in _conn.columns]
    return _response(200, [_row_to_dict(cols, row) for row in rows])


def _update_stock(event):
    if not (_groups(event) & _WRITE_ROLES):
        return _response(403, {"error": "Insufficient permissions"})
    vehicle_id = (event.get("pathParameters") or {}).get("vehicleId", "")
    body = json.loads(event.get("body") or "{}")
    status = body.get("status")
    if not status:
        return _response(400, {"error": "status is required"})
    if status not in _VALID_STATUSES:
        return _response(400, {"error": f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}"})
    try:
        rows = _conn.run(
            "INSERT INTO stock (vehicle_id, status, updated_at) "
            "VALUES (:vehicle_id::UUID, :status, NOW()) "
            "ON CONFLICT (vehicle_id) DO UPDATE "
            "SET status = EXCLUDED.status, order_id = NULL, updated_at = NOW() "
            "RETURNING vehicle_id, status, order_id, updated_at",
            vehicle_id=vehicle_id,
            status=status,
        )
        cols = [c["name"] for c in _conn.columns]
        return _response(200, _row_to_dict(cols, rows[0]))
    except pg8000.native.DatabaseError:
        return _response(500, {"error": "Could not update stock"})


def _check_stock(event):
    vehicle_id = event.get("vehicleId", "")
    rows = _conn.run(
        f"{_SELECT} WHERE vehicle_id = :vehicle_id::UUID",
        vehicle_id=vehicle_id,
    )
    if not rows or rows[0][1] != "available":
        raise StockUnavailableError(f"Vehicle {vehicle_id} is not available")
    cols = [c["name"] for c in _conn.columns]
    return _row_to_dict(cols, rows[0])


def _reserve_stock(event):
    vehicle_id = event.get("vehicleId", "")
    order_id = event.get("orderId", "")
    rows = _conn.run(
        "UPDATE stock SET status = 'reserved', order_id = :order_id::UUID, updated_at = NOW() "
        "WHERE vehicle_id = :vehicle_id::UUID AND status = 'available' "
        "RETURNING vehicle_id, status, order_id, updated_at",
        vehicle_id=vehicle_id,
        order_id=order_id,
    )
    if not rows:
        raise StockUnavailableError(f"Vehicle {vehicle_id} is not available for reservation")
    cols = [c["name"] for c in _conn.columns]
    return _row_to_dict(cols, rows[0])


def _release_stock(event):
    vehicle_id = event.get("vehicleId", "")
    order_id = event.get("orderId", "")
    rows = _conn.run(
        "UPDATE stock SET status = 'available', order_id = NULL, updated_at = NOW() "
        "WHERE vehicle_id = :vehicle_id::UUID AND order_id = :order_id::UUID "
        "RETURNING vehicle_id, status, order_id, updated_at",
        vehicle_id=vehicle_id,
        order_id=order_id,
    )
    cols = [c["name"] for c in _conn.columns]
    if rows:
        return _row_to_dict(cols, rows[0])
    return {"vehicleId": vehicle_id, "status": "available", "orderId": None, "updatedAt": None}


def handler(event, context):
    action = event.get("action")
    if action:
        if action == "checkStock":
            return _check_stock(event)
        if action == "reserveStock":
            return _reserve_stock(event)
        if action == "releaseStock":
            return _release_stock(event)
        raise ValueError(f"Unknown action: {action}")

    route = event.get("routeKey", "")
    if route == "GET /stock":
        return _list_stock(event)
    if route == "PUT /stock/{vehicleId}":
        return _update_stock(event)

    return _response(404, {"error": "Route not found"})
