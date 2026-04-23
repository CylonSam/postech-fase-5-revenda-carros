variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  type        = string
}

variable "cognito_issuer_url" {
  description = "Cognito JWT issuer URL"
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito User Pool Client ID (JWT audience)"
  type        = string
}

variable "lambda_invoke_arns" {
  description = "Map of Lambda function name to invoke ARN"
  type        = map(string)
}

variable "lambda_function_names" {
  description = "Map of Lambda function name to function name"
  type        = map(string)
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}
