output "endpoint" {
  value     = aws_db_instance.main.address
  sensitive = true
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "port" {
  value = aws_db_instance.main.port
}
