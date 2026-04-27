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
    CREATE TABLE IF NOT EXISTS vehicles (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        brand      VARCHAR(100) NOT NULL,
        model      VARCHAR(100) NOT NULL,
        year       INTEGER NOT NULL,
        color      VARCHAR(50) NOT NULL,
        price      INTEGER NOT NULL,
        plate      VARCHAR(20) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """
)

_SELECT = "SELECT id, brand, model, year, color, price, plate FROM vehicles"

_WRITE_ROLES = {"admin", "operator"}


def _groups(event):
    raw = event["requestContext"]["authorizer"]["jwt"]["claims"].get("cognito:groups", "")
    if not raw:
        return set()
    # API Gateway encodes Cognito group arrays as "[group1 group2]" (brackets, space-separated)
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
        "brand": d["brand"],
        "model": d["model"],
        "year": int(d["year"]),
        "color": d["color"],
        "price": int(d["price"]),
        "plate": d["plate"],
    }


def _validate_body(body):
    for field in ("brand", "model", "year", "color", "price", "plate"):
        if field not in body:
            return None, f"{field} is required"
    try:
        year = int(body["year"])
    except (ValueError, TypeError):
        return None, "year must be an integer"
    try:
        price = int(body["price"])
    except (ValueError, TypeError):
        return None, "price must be an integer"
    if not str(body["plate"]).strip():
        return None, "plate is required"
    return {
        "brand": str(body["brand"]).strip(),
        "model": str(body["model"]).strip(),
        "year": year,
        "color": str(body["color"]).strip(),
        "price": price,
        "plate": str(body["plate"]).strip(),
    }, None


def _is_unique_violation(exc):
    return (
        exc.args
        and isinstance(exc.args[0], dict)
        and exc.args[0].get("C") == "23505"
    )


def _list_vehicles(event):
    rows = _conn.run(f"{_SELECT} ORDER BY created_at DESC")
    cols = [c["name"] for c in _conn.columns]
    return _response(200, [_row_to_dict(cols, row) for row in rows])


def _get_vehicle(event):
    vehicle_id = (event.get("pathParameters") or {}).get("id", "")
    rows = _conn.run(f"{_SELECT} WHERE id = :id::UUID", id=vehicle_id)
    cols = [c["name"] for c in _conn.columns]
    if not rows:
        return _response(404, {"error": "Vehicle not found"})
    return _response(200, _row_to_dict(cols, rows[0]))


def _create_vehicle(event):
    if not (_groups(event) & _WRITE_ROLES):
        return _response(403, {"error": "Insufficient permissions"})
    body = json.loads(event.get("body") or "{}")
    data, err = _validate_body(body)
    if err:
        return _response(400, {"error": err})
    try:
        rows = _conn.run(
            "INSERT INTO vehicles (brand, model, year, color, price, plate) "
            "VALUES (:brand, :model, :year, :color, :price, :plate) "
            "RETURNING id, brand, model, year, color, price, plate",
            **data,
        )
        cols = [c["name"] for c in _conn.columns]
        return _response(201, _row_to_dict(cols, rows[0]))
    except pg8000.native.DatabaseError as e:
        if _is_unique_violation(e):
            return _response(409, {"error": "Plate already registered"})
        return _response(500, {"error": "Could not create vehicle"})


def _update_vehicle(event):
    if not (_groups(event) & _WRITE_ROLES):
        return _response(403, {"error": "Insufficient permissions"})
    vehicle_id = (event.get("pathParameters") or {}).get("id", "")
    body = json.loads(event.get("body") or "{}")
    data, err = _validate_body(body)
    if err:
        return _response(400, {"error": err})
    try:
        rows = _conn.run(
            "UPDATE vehicles SET brand=:brand, model=:model, year=:year, "
            "color=:color, price=:price, plate=:plate "
            "WHERE id = :id::UUID "
            "RETURNING id, brand, model, year, color, price, plate",
            id=vehicle_id,
            **data,
        )
        cols = [c["name"] for c in _conn.columns]
        if not rows:
            return _response(404, {"error": "Vehicle not found"})
        return _response(200, _row_to_dict(cols, rows[0]))
    except pg8000.native.DatabaseError as e:
        if _is_unique_violation(e):
            return _response(409, {"error": "Plate already registered"})
        return _response(500, {"error": "Could not update vehicle"})


def handler(event, context):
    route = event.get("routeKey", "")

    if route == "GET /vehicles":
        return _list_vehicles(event)
    if route == "GET /vehicles/{id}":
        return _get_vehicle(event)
    if route == "POST /vehicles":
        return _create_vehicle(event)
    if route == "PUT /vehicles/{id}":
        return _update_vehicle(event)

    return _response(404, {"error": "Route not found"})
