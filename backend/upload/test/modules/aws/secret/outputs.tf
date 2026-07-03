output "arn" {
  description = "ARN of the Secrets Manager secret."
  value       = aws_secretsmanager_secret.this.arn
}

output "name" {
  description = "Name/path of the Secrets Manager secret."
  value       = aws_secretsmanager_secret.this.name
}
