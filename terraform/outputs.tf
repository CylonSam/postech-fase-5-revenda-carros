output "api_gateway_url" {
  description = "Base URL for the API Gateway"
  value       = module.api_gateway.invoke_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.cognito.client_id
}

output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = module.rds.endpoint
  sensitive   = true
}

output "sqs_queue_url" {
  description = "URL of the SQS payment queue"
  value       = module.sqs.queue_url
}

output "step_function_arn" {
  description = "ARN of the Step Functions state machine"
  value       = module.step_functions.state_machine_arn
}

output "lambda_function_names" {
  description = "Map of Lambda function names"
  value       = module.lambda.function_names
}
