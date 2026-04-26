locals {
  _placeholder = "${path.module}/../../../lambda_placeholders/index.py"

  functions = {
    auth = {
      timeout = 30
      memory  = 128
    }
    user = {
      timeout = 30
      memory  = 128
    }
    vehicles = {
      timeout = 30
      memory  = 128
    }
    orders = {
      timeout = 60
      memory  = 256
    }
    stock = {
      timeout = 60
      memory  = 256
    }
  }

  _single_file_sources = {
    auth   = "${path.module}/../../../lambdas/auth/index.py"
    user   = "${path.module}/../../../lambdas/user/index.py"
    orders = local._placeholder
    stock  = local._placeholder
  }
}

data "archive_file" "single_file_functions" {
  for_each    = local._single_file_sources
  type        = "zip"
  source_file = each.value
  output_path = "${path.module}/archives/${each.key}.zip"
}

data "archive_file" "vehicles" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/vehicles"
  excludes    = ["test_index.py", "requirements.txt"]
  output_path = "${path.module}/archives/vehicles.zip"
}

locals {
  _archives = merge(
    { for k, v in data.archive_file.single_file_functions : k => v },
    { vehicles = data.archive_file.vehicles }
  )
}

resource "aws_lambda_function" "functions" {
  for_each = local.functions

  function_name = "${var.name_prefix}-${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = var.runtime
  handler       = "index.handler"
  timeout       = each.value.timeout
  memory_size   = each.value.memory

  filename         = local._archives[each.key].output_path
  source_code_hash = local._archives[each.key].output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_sg_id]
  }

  environment {
    variables = {
      DB_ENDPOINT          = var.db_endpoint
      DB_NAME              = var.db_name
      DB_PORT              = "5432"
      DB_USERNAME          = var.db_username
      DB_PASSWORD          = var.db_password
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
