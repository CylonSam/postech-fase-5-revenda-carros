data "aws_caller_identity" "current" {}

# Compute the Step Functions ARN ahead of time using known naming convention
# to avoid a circular dependency between the lambda and step_functions modules.
locals {
  step_function_arn = "arn:aws:states:${var.aws_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${local.name_prefix}-car-sale-saga"
}

module "vpc" {
  source      = "./modules/vpc"
  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
}

module "cognito" {
  source      = "./modules/cognito"
  name_prefix = local.name_prefix
}

module "rds" {
  source             = "./modules/rds"
  name_prefix        = local.name_prefix
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  rds_sg_id          = module.vpc.rds_sg_id
  db_name            = var.db_name
  db_username        = var.db_username
  db_password        = var.db_password
  instance_class     = var.db_instance_class
}

module "sqs" {
  source      = "./modules/sqs"
  name_prefix = local.name_prefix
}

module "lambda" {
  source                = "./modules/lambda"
  name_prefix           = local.name_prefix
  runtime               = var.lambda_runtime
  private_subnet_ids    = module.vpc.private_subnet_ids
  lambda_sg_id          = module.vpc.lambda_sg_id
  db_endpoint           = module.rds.endpoint
  db_name               = var.db_name
  sqs_queue_url         = module.sqs.queue_url
  sqs_queue_arn         = module.sqs.queue_arn
  step_function_arn     = local.step_function_arn
  cognito_user_pool_id  = module.cognito.user_pool_id
  cognito_client_id     = module.cognito.client_id
  cognito_user_pool_arn = module.cognito.user_pool_arn
  db_username           = var.db_username
  db_password           = var.db_password
}

module "step_functions" {
  source        = "./modules/step_functions"
  name_prefix   = local.name_prefix
  lambda_arns   = module.lambda.function_arns
  sqs_queue_arn = module.sqs.queue_arn
  sqs_queue_url = module.sqs.queue_url
  aws_region    = var.aws_region
}

module "api_gateway" {
  source                = "./modules/api_gateway"
  name_prefix           = local.name_prefix
  cognito_user_pool_id  = module.cognito.user_pool_id
  cognito_issuer_url    = module.cognito.issuer_url
  cognito_client_id     = module.cognito.client_id
  lambda_invoke_arns    = module.lambda.invoke_arns
  lambda_function_names = module.lambda.function_names
  aws_region            = var.aws_region
}
