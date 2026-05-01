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
        price      NUMERIC(12,2) NOT NULL,
        plate      VARCHAR(20) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """
)

_conn.run(
    """
    CREATE TABLE IF NOT EXISTS orders (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        customer_id       UUID NOT NULL,
        vehicle_id        UUID NOT NULL,
        status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'confirmed', 'failed', 'refunded', 'delivered')),
        amount            NUMERIC(12,2) NOT NULL,
        retriever_license TEXT,
        retriever_tax_id  TEXT,
        created_at        TIMESTAMP DEFAULT NOW(),
        updated_at        TIMESTAMP DEFAULT NOW()
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

_SELECT = """
    SELECT
        o.id,
        o.customer_id,
        o.status,
        o.amount,
        o.created_at,
        o.retriever_license,
        o.retriever_tax_id,
        v.brand,
        v.model,
        v.year,
        v.color,
        v.plate,
        v.price,
        p.payment_code,
        p.status AS payment_status
    FROM orders o
    JOIN vehicles v ON v.id = o.vehicle_id
    LEFT JOIN LATERAL (
        SELECT payment_code, status
        FROM payments
        WHERE order_id = o.id
        ORDER BY created_at DESC
        LIMIT 1
    ) p ON true
    WHERE o.id = :order_id::UUID
"""


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


def _row_to_doc(cols, row):
    d = dict(zip(cols, row))
    retriever = None
    if d.get("retriever_license") or d.get("retriever_tax_id"):
        retriever = {
            "license": d["retriever_license"],
            "taxId": d["retriever_tax_id"],
        }
    payment = None
    if d.get("payment_code") is not None:
        payment = {
            "code": str(d["payment_code"]),
            "status": d["payment_status"],
        }
    return {
        "orderId": str(d["id"]),
        "status": d["status"],
        "createdAt": d["created_at"].isoformat() if d["created_at"] else None,
        "customerId": str(d["customer_id"]),
        "vehicle": {
            "brand": d["brand"],
            "model": d["model"],
            "year": int(d["year"]),
            "color": d["color"],
            "plate": d["plate"],
            "price": float(d["price"]),
        },
        "retriever": retriever,
        "payment": payment,
    }


def _get_doc(event):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    customer_id = claims.get("sub", "")
    order_id = (event.get("pathParameters") or {}).get("orderId", "")
    try:
        rows = _conn.run(_SELECT, order_id=order_id)
        cols = [c["name"] for c in _conn.columns]
    except pg8000.native.DatabaseError:
        return _response(500, {"error": "Could not retrieve order"})

    if not rows:
        return _response(404, {"error": "Order not found"})

    doc = _row_to_doc(cols, rows[0])
    if doc["customerId"] != customer_id and not (_groups(event) & _ADMIN_ROLES):
        return _response(403, {"error": "Access denied"})

    return _response(200, doc)


def handler(event, context):
    route = event.get("routeKey", "")
    if route == "GET /docs/{orderId}":
        return _get_doc(event)
    return _response(404, {"error": "Route not found"})
