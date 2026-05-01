# Car Dealership — POS Tech Fase 5

Serverless car resale platform built on AWS with Terraform and GitHub Actions. Customers can browse vehicles, place purchase orders, and receive a sale document upon completion. Administrators manage inventory and confirm deliveries.

## Architecture

```
Client → API Gateway (HTTP v2, Cognito JWT) → Lambda → PostgreSQL (RDS, private VPC)
                                                  ↓
                                        Step Functions (Car Sale Saga)
                                                  ↓
                                      SQS → Lambda (payment callback)
```

**Infrastructure modules** (`terraform/modules/`):

| Module | Purpose |
|---|---|
| `vpc` | VPC, public/private subnets, NAT gateway |
| `cognito` | User pool, app client, groups (`admin`, `operator`, `client`) |
| `rds` | PostgreSQL 15 on `db.t3.micro`, private subnets only |
| `sqs` | Queue for Step Functions async payment task token |
| `lambda` | All Lambda functions + shared IAM execution role |
| `step_functions` | Car Sale Saga state machine |
| `api_gateway` | HTTP API v2, Cognito JWT authorizer, routes |

**Authentication:** Cognito JWT. Pass `Authorization: Bearer <id_token>` on protected routes.  
**User groups:** `admin` and `operator` have elevated access; `client` is the default self-registered role.

## API Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Register a new user |
| POST | `/auth/login` | No | Login, returns Cognito tokens |
| GET | `/users/{id}` | Yes | Get own Cognito profile |
| PUT | `/users/{id}` | Yes | Update own profile |
| GET | `/vehicles` | No | List all vehicles |
| GET | `/vehicles/{id}` | No | Get vehicle by ID |
| POST | `/vehicles` | Yes (admin/operator) | Create vehicle |
| PUT | `/vehicles/{id}` | Yes (admin/operator) | Update vehicle |
| POST | `/orders` | Yes | Create order and start sale saga |
| GET | `/orders` | Yes | List orders (own; all for admin/operator) |
| GET | `/orders/{id}` | Yes | Get order details |
| GET | `/orders/{id}/payment` | Yes | Get payment status |
| PUT | `/orders/{id}/retriever` | Yes | Set vehicle retriever info |
| POST | `/orders/{id}/pickup` | Yes (admin/operator) | Mark order as delivered |
| PUT | `/users/{id}/license` | Yes | Register driver's license |
| POST | `/payments/webhook` | No | Payment gateway callback |
| GET | `/stock` | No | List vehicle stock |
| PUT | `/stock/{vehicleId}` | Yes (admin/operator) | Update stock status |
| GET | `/docs/{orderId}` | Yes | Get sale document for an order |

## Local Development

```bash
# Install test dependencies
pip install -r lambdas/requirements-test.txt

# Run all tests
pytest lambdas/ -v --tb=short

# Run a single lambda's tests
pytest lambdas/docs/test_index.py -v --tb=short

# Terraform (from terraform/)
terraform fmt -check -recursive
terraform init -backend=false
TF_VAR_db_username=x TF_VAR_db_password=x terraform validate

# Install pg8000 into lambda directories (required before terraform plan/apply)
pip install pg8000 -t lambdas/vehicles/ --quiet
pip install pg8000 -t lambdas/stock/ --quiet
pip install pg8000 -t lambdas/orders/ --quiet
pip install pg8000 -t lambdas/docs/ --quiet
```

## CI/CD

GitHub Actions (`.github/workflows/terraform.yml`) runs on push/PR to `main`:

| Job | Trigger | Description |
|---|---|---|
| `test` | Always | `pytest lambdas/` with Python 3.12 |
| `validate` | Always | `terraform fmt` + `terraform validate` (no AWS credentials needed) |
| `plan` | After test + validate | OIDC auth, installs pg8000, runs `terraform plan`, posts diff as PR comment |
| `apply` | `workflow_dispatch` on `main` only | Downloads plan artifact and runs `terraform apply` |

Required GitHub secrets: `AWS_ROLE_ARN`, `TF_BACKEND_BUCKET`, `TF_BACKEND_KEY`, `TF_BACKEND_REGION`, `TF_VAR_db_password`, `TF_VAR_db_username`.
