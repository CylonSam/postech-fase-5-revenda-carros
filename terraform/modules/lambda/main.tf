locals {
  _placeholder = "${path.module}/../../../lambda_placeholders/index.py"

  functions = {
    auth = {
      timeout = 30
      memory  = 128
      source  = "${path.module}/../../../lambdas/auth/index.py"
    }
    user = {
      timeout = 30
      memory  = 128
      source  = "${path.module}/../../../lambdas/user/index.py"
    }
    vehicles = {
      timeout = 30
      memory  = 128
      source  = local._placeholder
    }
    orders = {
      timeout = 60
      memory  = 256
      source  = local._placeholder
    }
    stock = {
      timeout = 60
      memory  = 256
      source  = local._placeholder
    }
  }
}

data "archive_file" "functions" {
  for_each    = local.functions
  type        = "zip"
  source_file = each.value.source
  output_path = "${path.module}/archives/${each.key}.zip"
}

resource "aws_lambda_function" "functions" {
  for_each = local.functions

  function_name = "${var.name_prefix}-${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = var.runtime
  handler       = "index.handler"
  timeout       = each.value.timeout
  memory_size   = each.value.memory

  filename         = data.archive_file.functions[each.key].output_path
  source_code_hash = data.archive_file.functions[each.key].output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_sg_id]
  }

  environment {
    variables = {
      DB_ENDPOINT          = var.db_endpoint
      DB_NAME              = var.db_name
      DB_PORT              = "5432"
      SQS_QUEUE_URL        = var.sqs_queue_url
      STEP_FUNCTION_ARN    = var.step_function_arn
      COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      COGNITO_CLIENT_ID    = var.cognito_client_id
    }
  }

  tags = {
    Name     = "${var.name_prefix}-${each.key}"
    Function = each.key
  }
}

# SQS trigger on the orders Lambda (payment callback consumer)
resource "aws_lambda_event_source_mapping" "sqs_orders" {
  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.functions["orders"].arn
  batch_size       = 1
  enabled          = true
}
