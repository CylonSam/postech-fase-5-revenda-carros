output "queue_url" {
  value = aws_sqs_queue.payment.url
}

output "queue_arn" {
  value = aws_sqs_queue.payment.arn
}

output "dlq_arn" {
  value = aws_sqs_queue.payment_dlq.arn
}
