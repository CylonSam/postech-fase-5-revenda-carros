data "aws_caller_identity" "current" {}

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }

  tags = {
    Name = "${var.name_prefix}-api"
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gw.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }
}

resource "aws_cloudwatch_log_group" "api_gw" {
  name              = "/aws/apigateway/${var.name_prefix}"
  retention_in_days = 7
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name_prefix}-cognito-authorizer"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = var.cognito_issuer_url
  }
}

# ── Integrations ──────────────────────────────────────────────────────────────

resource "aws_apigatewayv2_integration" "functions" {
  for_each = var.lambda_invoke_arns

  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value
  payload_format_version = "2.0"
}

# ── Lambda permissions ────────────────────────────────────────────────────────

resource "aws_lambda_permission" "api_gw" {
  for_each = var.lambda_function_names

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── Routes ────────────────────────────────────────────────────────────────────

locals {
  # [method, path, integration_key, requires_auth]
  routes = [
    ["POST", "/auth/login", "auth", false],
    ["POST", "/auth/register", "auth", false],
    ["GET", "/users/{id}", "user", true],
    ["PUT", "/users/{id}", "user", true],
    ["GET", "/vehicles", "vehicles", false],
    ["GET", "/vehicles/{id}", "vehicles", false],
    ["POST", "/vehicles", "vehicles", true],
    ["PUT", "/vehicles/{id}", "vehicles", true],
    ["POST", "/orders", "orders", true],
    ["GET", "/orders", "orders", true],
    ["GET", "/orders/{id}", "orders", true],
    ["GET", "/stock", "stock", false],
    ["PUT", "/stock/{vehicleId}", "stock", true],
  ]

  routes_map = {
    for r in local.routes :
    "${r[0]} ${r[1]}" => {
      method       = r[0]
      path         = r[1]
      function_key = r[2]
      auth         = r[3]
    }
  }
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = local.routes_map

  api_id    = aws_apigatewayv2_api.main.id
  route_key = "${each.value.method} ${each.value.path}"

  target = "integrations/${aws_apigatewayv2_integration.functions[each.value.function_key].id}"

  authorization_type = each.value.auth ? "JWT" : "NONE"
  authorizer_id      = each.value.auth ? aws_apigatewayv2_authorizer.cognito.id : null
}
