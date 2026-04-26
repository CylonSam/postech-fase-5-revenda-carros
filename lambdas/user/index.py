import json
import os

import boto3
from botocore.exceptions import ClientError

cognito = boto3.client("cognito-idp")

USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _claims(event):
    return event["requestContext"]["authorizer"]["jwt"]["claims"]


def _authorized(event):
    """Returns (sub, email) if the path id matches the caller's sub, else None."""
    claims = _claims(event)
    sub = claims.get("sub", "")
    email = claims.get("email", "")
    path_id = (event.get("pathParameters") or {}).get("id", "")
    if path_id != sub:
        return None, None
    return sub, email


def _attrs_to_dict(attributes):
    return {a["Name"]: a["Value"] for a in attributes}


def _get_user(event):
    sub, email = _authorized(event)
    if not sub:
        return _response(403, {"error": "Access denied"})

    try:
        result = cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=email)
        attrs = _attrs_to_dict(result["UserAttributes"])
        return _response(
            200,
            {
                "sub": sub,
                "email": attrs.get("email", email),
                "name": attrs.get("name", ""),
            },
        )
    except ClientError:
        return _response(500, {"error": "Could not retrieve user"})


def _update_user(event):
    sub, email = _authorized(event)
    if not sub:
        return _response(403, {"error": "Access denied"})

    body = json.loads(event.get("body") or "{}")
    name = body.get("name", "").strip()
    if not name:
        return _response(400, {"error": "name is required"})

    try:
        cognito.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[{"Name": "name", "Value": name}],
        )
        return _response(200, {"message": "User updated"})
    except ClientError:
        return _response(500, {"error": "Could not update user"})


def handler(event, context):
    route = event.get("routeKey", "")

    if route == "GET /users/{id}":
        return _get_user(event)
    if route == "PUT /users/{id}":
        return _update_user(event)

    return _response(404, {"error": "Route not found"})
