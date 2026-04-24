locals {
  functions = {
    user = {
      timeout = 30
      memory  = 128
    }
    auth = {
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
}

data "archive_file" "placeholder" {
  type        = "zip"
  source_file = "${path.module}/../../../lambda_placeholders/index.py"
  output_path = "${path.module}/../../../lambda_placeholders/placeholder.zip"
}

resource "aws_lambda_function" "functions" {
  for_each = local.functions

  function_name = "${var.name_prefix}-${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = var.runtime
  handler       = "index.handler" # index.py → handler()
  timeout       = each.value.timeout
  memory_size   = each.value.memory

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_sg_id]
  }

  environment {
    variables = {
      DB_ENDPOINT       = var.db_endpoint
      DB_NAME           = var.db_name
      DB_PORT           = "5432"
      SQS_QUEUE_URL     = var.sqs_queue_url
      STEP_FUNCTION_ARN = var.step_function_arn
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
