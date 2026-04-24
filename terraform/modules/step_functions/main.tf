resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/states/${var.name_prefix}-car-sale-saga"
  retention_in_days = 7
}

resource "aws_sfn_state_machine" "car_sale_saga" {
  name     = "${var.name_prefix}-car-sale-saga"
  role_arn = aws_iam_role.sfn_exec.arn
  type     = "EXPRESS"

  definition = templatefile("${path.module}/state_machine.json.tpl", {
    orders_lambda_arn = var.lambda_arns["orders"]
    stock_lambda_arn  = var.lambda_arns["stock"]
    sqs_queue_url     = var.sqs_queue_url
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  tags = {
    Name = "${var.name_prefix}-car-sale-saga"
  }
}
