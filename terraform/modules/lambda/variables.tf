variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "nodejs20.x"
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for Lambda VPC config"
  type        = list(string)
}

variable "lambda_sg_id" {
  description = "Security group ID for Lambda functions"
  type        = string
}

variable "db_endpoint" {
  description = "RDS endpoint"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "sqs_queue_url" {
  description = "URL of the SQS payment queue"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS payment queue"
  type        = string
}

variable "step_function_arn" {
  description = "ARN of the Step Functions state machine"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito App Client ID"
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN (used to scope IAM permissions)"
  type        = string
}

variable "db_username" {
  description = "Database username"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}
