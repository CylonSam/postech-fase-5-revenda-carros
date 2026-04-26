import json
import os

import boto3
from botocore.exceptions import ClientError

cognito = boto3.client("cognito-idp")

USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]

_CLIENT_ERROR_TO_STATUS = {
    "UsernameExistsException": (409, "Email already registered"),
    "InvalidPasswordException": (400, "Password does not meet requirements"),
    "InvalidParameterException": (400, "Invalid parameters"),
    "NotAuthorizedException": (401, "Invalid email or password"),
    "UserNotFoundException": (401, "Invalid email or password"),
    "UserNotConfirmedException": (401, "User not confirmed"),
}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _error(exc):
    code = exc.response["Error"]["Code"]
    status, message = _CLIENT_ERROR_TO_STATUS.get(code, (500, "Internal server error"))
    return _response(status, {"error": message})


def _register(body):
    email = body.get("email", "").strip()
    password = body.get("password", "")
    name = body.get("name", "").strip()

    if not email or not password or not name:
        return _response(400, {"error": "email, password and name are required"})

    try:
        result = cognito.sign_up(
            ClientId=CLIENT_ID,
            Username=email,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": name},
            ],
        )
        # Auto-confirm so callers can log in immediately without email verification
        cognito.admin_confirm_sign_up(UserPoolId=USER_POOL_ID, Username=email)
        return _response(201, {"message": "User registered", "user_sub": result["UserSub"]})
    except ClientError as exc:
        return _error(exc)


def _login(body):
    email = body.get("email", "").strip()
    password = body.get("password", "")

    if not email or not password:
        return _response(400, {"error": "email and password are required"})

    try:
        result = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            ClientId=CLIENT_ID,
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        tokens = result["AuthenticationResult"]
        return _response(
            200,
            {
                "access_token": tokens["AccessToken"],
                "id_token": tokens["IdToken"],
                "refresh_token": tokens["RefreshToken"],
                "expires_in": tokens["ExpiresIn"],
            },
        )
    except ClientError as exc:
        return _error(exc)


def handler(event, context):
    route = event.get("routeKey", "")
    body = json.loads(event.get("body") or "{}")

    if route == "POST /auth/register":
        return _register(body)
    if route == "POST /auth/login":
        return _login(body)

    return _response(404, {"error": "Route not found"})
