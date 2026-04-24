output "state_machine_arn" {
  value = aws_sfn_state_machine.car_sale_saga.arn
}

output "state_machine_name" {
  value = aws_sfn_state_machine.car_sale_saga.name
}
