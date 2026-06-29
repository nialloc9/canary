output "ecr_repository_url" {
  value = aws_ecr_repository.repo.repository_url
}

output "batch_job_queue" {
  value = aws_batch_job_queue.queue.name
}

output "batch_job_definition" {
  value = aws_batch_job_definition.job.name
}
