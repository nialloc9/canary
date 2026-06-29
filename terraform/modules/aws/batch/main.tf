resource "random_string" "random_string" {
  length  = 5
  special = false
  upper   = false
}

###################################
# ECR Repository
###################################
resource "aws_ecr_repository" "repo" {
  name = "${local.unique_name}-repo"

  image_scanning_configuration {
    scan_on_push = true
  }
}

###################################
# IAM Roles
###################################
resource "aws_iam_role" "batch_service_role" {
  name = "${local.unique_name}-batch-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "batch.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "batch_service_role" {
  role       = aws_iam_role.batch_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}

resource "aws_iam_role" "ecs_instance_role" {
  name = "${local.unique_name}-ecs-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_instance_role" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "ecs_instance_profile" {
  name = "${local.unique_name}-ecs-instance-profile"
  role = aws_iam_role.ecs_instance_role.name
}


###################################
# Batch Compute Environment (SPOT)
###################################
resource "aws_batch_compute_environment" "spot" {
  name = "${local.unique_name}-spot-ce"
  service_role             = aws_iam_role.batch_service_role.arn
  type                     = "MANAGED"

  compute_resources {
    type                = "SPOT"
    allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"

    max_vcpus     = var.max_vcpus
    desired_vcpus = var.desired_vcpus
    min_vcpus     = 0

    instance_type = var.instance_types
    
    subnets        = var.subnets
    security_group_ids = var.security_groups

    instance_role = aws_iam_instance_profile.ecs_instance_profile.arn
  }
}

###################################
# Job Queue
###################################
resource "aws_batch_job_queue" "queue" {
  name     = "${local.unique_name}-queue"
  state = "ENABLED"
  priority = 1

compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.spot.arn
  }

}

###################################
# Job Definition
###################################
resource "aws_batch_job_definition" "job" {
  name = "${local.unique_name}-job"
  type = "container"

  container_properties = jsonencode({
    image = aws_ecr_repository.repo.repository_url
    vcpus = 1
    memory = 1024
    command = ["echo", "hello"]
  })

  tags = local.tags
}
