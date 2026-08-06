terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

# ─────────────────────────────────────────────────────────────────────────────
# Variables (populated from TF_VAR_* GitHub Secrets)
# ─────────────────────────────────────────────────────────────────────────────

variable "aws_region"              { default = "us-east-1" }
variable "aws_account_id"          { sensitive = true }
variable "project_name"            { default = "linkedin-job-scout" }
variable "environment"             { default = "prod" }
variable "image_tag"               { default = "latest" }
variable "frontend_url"            {}
# Webhook validation token — needed as env var on every bot request, low-risk as env var
variable "telegram_webhook_secret" { sensitive = true }
# App secrets (API keys, passwords) live in Secrets Manager, not here
variable "secrets_name"            { default = "linkedin-job-scout/prod/secrets" }

locals {
  prefix   = "${var.project_name}-${var.environment}"
  ecr_base = "${var.aws_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${var.project_name}"
}

# ─────────────────────────────────────────────────────────────────────────────
# DynamoDB Tables
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_dynamodb_table" "users" {
  name         = "${local.prefix}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "email"
    type = "S"
  }
  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "searches" {
  name         = "${local.prefix}-searches"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "search_id"
  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "search_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "profiles" {
  name         = "${local.prefix}-profiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  attribute {
    name = "user_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "jobs" {
  name         = "${local.prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "job_id"
  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "job_id"
    type = "S"
  }
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "telegram_codes" {
  name         = "${local.prefix}-telegram-codes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "code"
  attribute {
    name = "code"
    type = "S"
  }
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "interviews" {
  name         = "${local.prefix}-interviews"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "interview_id"
  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "interview_id"
    type = "S"
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# IAM
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "lambda_exec" {
  name = "${local.prefix}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "app_policy" {
  name = "app-policy"
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          "${aws_dynamodb_table.users.arn}/index/*",
          aws_dynamodb_table.searches.arn,
          aws_dynamodb_table.profiles.arn,
          aws_dynamodb_table.jobs.arn,
          aws_dynamodb_table.telegram_codes.arn,
          aws_dynamodb_table.interviews.arn,
        ]
      },
      {
        # LinkedIn session cookies are stored/loaded at runtime from Secrets Manager
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue", "secretsmanager:CreateSecret"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "*"
      }
    ]
  })
}

# ─────────────────────────────────────────────────────────────────────────────
# Lambda Functions
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_lambda_function" "api" {
  function_name = "${local.prefix}-api"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${local.ecr_base}-api:${var.image_tag}"
  timeout       = 30
  memory_size   = 512
  environment {
    variables = {
      ENVIRONMENT          = var.environment
      FRONTEND_URL         = var.frontend_url
      SECRETS_NAME         = var.secrets_name
      USERS_TABLE          = aws_dynamodb_table.users.name
      SEARCHES_TABLE       = aws_dynamodb_table.searches.name
      PROFILES_TABLE       = aws_dynamodb_table.profiles.name
      JOBS_TABLE           = aws_dynamodb_table.jobs.name
      TELEGRAM_CODES_TABLE = aws_dynamodb_table.telegram_codes.name
      INTERVIEWS_TABLE     = aws_dynamodb_table.interviews.name
    }
  }
}

resource "aws_lambda_function" "scraper" {
  function_name = "${local.prefix}-scraper"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${local.ecr_base}-scraper:${var.image_tag}"
  timeout       = 600
  memory_size   = 2048
  environment {
    variables = {
      ENVIRONMENT              = var.environment
      SECRETS_NAME             = var.secrets_name
      USERS_TABLE              = aws_dynamodb_table.users.name
      SEARCHES_TABLE           = aws_dynamodb_table.searches.name
      PROFILES_TABLE           = aws_dynamodb_table.profiles.name
      JOBS_TABLE               = aws_dynamodb_table.jobs.name
      TELEGRAM_CODES_TABLE     = aws_dynamodb_table.telegram_codes.name
      MAX_SCORER_CALLS_PER_RUN = "150"
    }
  }
}

resource "aws_lambda_function" "telegram_bot" {
  function_name = "${local.prefix}-telegram-bot"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${local.ecr_base}-telegram-bot:${var.image_tag}"
  timeout       = 15
  memory_size   = 256
  environment {
    variables = {
      ENVIRONMENT             = var.environment
      SECRETS_NAME            = var.secrets_name
      USERS_TABLE             = aws_dynamodb_table.users.name
      SEARCHES_TABLE          = aws_dynamodb_table.searches.name
      PROFILES_TABLE          = aws_dynamodb_table.profiles.name
      JOBS_TABLE              = aws_dynamodb_table.jobs.name
      TELEGRAM_CODES_TABLE    = aws_dynamodb_table.telegram_codes.name
      TELEGRAM_WEBHOOK_SECRET = var.telegram_webhook_secret
    }
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# API Gateway HTTP API
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_apigatewayv2_api" "main" {
  name          = "${local.prefix}-api"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    allow_headers = ["Authorization", "Content-Type"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "api_proxy" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_integration" "telegram_bot" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.telegram_bot.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "telegram_webhook" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /webhook/telegram"
  target    = "integrations/${aws_apigatewayv2_integration.telegram_bot.id}"
}

resource "aws_lambda_permission" "api_gw_api" {
  statement_id  = "AllowAPIGatewayInvokeApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gw_bot" {
  statement_id  = "AllowAPIGatewayInvokeBot"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.telegram_bot.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ─────────────────────────────────────────────────────────────────────────────
# EventBridge (4x/day, Mon–Fri)
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_event_rule" "scraper_schedule" {
  name                = "${local.prefix}-scraper-schedule"
  schedule_expression = "cron(0 12,16,20,23 ? * MON-FRI *)"
}

resource "aws_cloudwatch_event_target" "scraper" {
  rule = aws_cloudwatch_event_rule.scraper_schedule.name
  arn  = aws_lambda_function.scraper.arn
}

resource "aws_lambda_permission" "eventbridge_scraper" {
  statement_id  = "AllowEventBridgeInvokeScraper"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scraper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scraper_schedule.arn
}

# ─────────────────────────────────────────────────────────────────────────────
# CloudWatch Log Groups
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${aws_lambda_function.scraper.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "telegram_bot" {
  name              = "/aws/lambda/${aws_lambda_function.telegram_bot.function_name}"
  retention_in_days = 14
}

# ─────────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────────

output "api_url" {
  value       = aws_apigatewayv2_api.main.api_endpoint
  description = "Set as NEXT_PUBLIC_API_URL in Vercel"
}

output "telegram_webhook_url" {
  value       = "${aws_apigatewayv2_api.main.api_endpoint}/webhook/telegram"
  description = "Registered automatically with Telegram by the workflow"
}
