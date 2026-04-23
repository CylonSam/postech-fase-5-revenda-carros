variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "lambda_arns" {
  description = "Map of Lambda function name to ARN"
  type        = map(string)
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS payment queue"
  type        = string
}

variable "sqs_queue_url" {
  description = "URL of the SQS payment queue"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}
