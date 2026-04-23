resource "aws_sqs_queue" "payment_dlq" {
  name                       = "${var.name_prefix}-payment-dlq"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 30

  tags = {
    Name = "${var.name_prefix}-payment-dlq"
  }
}

resource "aws_sqs_queue" "payment" {
  name                       = "${var.name_prefix}-payment-queue"
  visibility_timeout_seconds = 300 # matches Lambda timeout
  message_retention_seconds  = 86400
  delay_seconds              = 0
  max_message_size           = 262144

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.payment_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.name_prefix}-payment-queue"
  }
}
