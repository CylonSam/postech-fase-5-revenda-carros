output "invoke_arns" {
  description = "Map of function name to invoke ARN (for API Gateway)"
  value       = { for k, v in aws_lambda_function.functions : k => v.invoke_arn }
}

output "function_arns" {
  description = "Map of function name to ARN (for Step Functions)"
  value       = { for k, v in aws_lambda_function.functions : k => v.arn }
}

output "function_names" {
  description = "Map of function name to function name (for reference)"
  value       = { for k, v in aws_lambda_function.functions : k => v.function_name }
}
