data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn_exec" {
  name               = "${var.name_prefix}-sfn-exec-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json
}

data "aws_iam_policy_document" "sfn_custom" {
  statement {
    sid    = "InvokeLambda"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      var.lambda_arns["orders"],
      var.lambda_arns["stock"],
    ]
  }

  statement {
    sid       = "SQSSendMessage"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutLogEvents",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "sfn_custom" {
  name   = "${var.name_prefix}-sfn-policy"
  policy = data.aws_iam_policy_document.sfn_custom.json
}

resource "aws_iam_role_policy_attachment" "sfn_custom" {
  role       = aws_iam_role.sfn_exec.name
  policy_arn = aws_iam_policy.sfn_custom.arn
}
