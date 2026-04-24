{
  "Comment": "Car Sale Saga Orchestration — coordinates the full car purchase transaction",
  "StartAt": "ValidateOrder",
  "States": {
    "ValidateOrder": {
      "Type": "Task",
      "Resource": "${orders_lambda_arn}",
      "Parameters": {
        "action": "validateOrder",
        "order.$": "$.order"
      },
      "ResultPath": "$.validation",
      "TimeoutSeconds": 30,
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"],
          "IntervalSeconds": 2,
          "MaxAttempts": 2,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "OrderFailed",
          "ResultPath": "$.error"
        }
      ],
      "Next": "CheckStock"
    },
    "CheckStock": {
      "Type": "Task",
      "Resource": "${stock_lambda_arn}",
      "Parameters": {
        "action": "checkStock",
        "vehicleId.$": "$.order.vehicleId"
      },
      "ResultPath": "$.stockCheck",
      "TimeoutSeconds": 30,
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"],
          "IntervalSeconds": 2,
          "MaxAttempts": 2,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["StockUnavailableError"],
          "Next": "OrderFailed",
          "ResultPath": "$.error"
        },
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "OrderFailed",
          "ResultPath": "$.error"
        }
      ],
      "Next": "ReserveStock"
    },
    "ReserveStock": {
      "Type": "Task",
      "Resource": "${stock_lambda_arn}",
      "Parameters": {
        "action": "reserveStock",
        "vehicleId.$": "$.order.vehicleId",
        "orderId.$": "$.order.id"
      },
      "ResultPath": "$.stockReservation",
      "TimeoutSeconds": 30,
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "OrderFailed",
          "ResultPath": "$.error"
        }
      ],
      "Next": "ProcessPayment"
    },
    "ProcessPayment": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Parameters": {
        "QueueUrl": "${sqs_queue_url}",
        "MessageBody": {
          "taskToken.$": "$$.Task.Token",
          "orderId.$": "$.order.id",
          "amount.$": "$.order.amount",
          "customerId.$": "$.order.customerId"
        }
      },
      "ResultPath": "$.payment",
      "TimeoutSeconds": 300,
      "HeartbeatSeconds": 60,
      "Catch": [
        {
          "ErrorEquals": ["PaymentFailedError", "States.HeartbeatTimeout"],
          "Next": "CompensateStock",
          "ResultPath": "$.error"
        },
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "CompensateStock",
          "ResultPath": "$.error"
        }
      ],
      "Next": "ConfirmOrder"
    },
    "ConfirmOrder": {
      "Type": "Task",
      "Resource": "${orders_lambda_arn}",
      "Parameters": {
        "action": "confirmOrder",
        "orderId.$": "$.order.id",
        "payment.$": "$.payment"
      },
      "ResultPath": "$.confirmation",
      "TimeoutSeconds": 30,
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "CompensatePayment",
          "ResultPath": "$.error"
        }
      ],
      "Next": "OrderSucceeded"
    },
    "OrderSucceeded": {
      "Type": "Succeed"
    },
    "CompensatePayment": {
      "Type": "Task",
      "Resource": "${orders_lambda_arn}",
      "Parameters": {
        "action": "refundPayment",
        "orderId.$": "$.order.id",
        "payment.$": "$.payment"
      },
      "ResultPath": "$.compensationPayment",
      "TimeoutSeconds": 30,
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "CompensateStock",
          "ResultPath": "$.compensationError"
        }
      ],
      "Next": "CompensateStock"
    },
    "CompensateStock": {
      "Type": "Task",
      "Resource": "${stock_lambda_arn}",
      "Parameters": {
        "action": "releaseStock",
        "vehicleId.$": "$.order.vehicleId",
        "orderId.$": "$.order.id"
      },
      "ResultPath": "$.compensationStock",
      "TimeoutSeconds": 30,
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "OrderFailed",
          "ResultPath": "$.compensationError"
        }
      ],
      "Next": "OrderFailed"
    },
    "OrderFailed": {
      "Type": "Fail",
      "Error": "OrderFailed",
      "Cause": "The car sale saga failed. Check execution history for details."
    }
  }
}
