# AWS Batch Terraform Module

A reusable Terraform module for creating AWS Batch resources including compute environments, job queues, IAM roles, and security groups.

## Features

- Supports both Fargate and EC2 compute environments
- Configurable spot instances for EC2
- Automatic IAM role creation or use existing roles
- Security group management
- Flexible compute resource configuration
- Full tagging support

## Usage

### Basic Fargate Example

```hcl
module "batch" {
  source = "./modules/batch"

  name       = "my-batch"
  vpc_id     = "vpc-12345678"
  subnet_ids = ["subnet-12345678", "subnet-87654321"]

  compute_environment_type = "FARGATE"
  max_vcpus                = 256

  tags = {
    Environment = "production"
    Project     = "my-project"
  }
}
```

### EC2 with Spot Instances Example

```hcl
module "batch" {
  source = "./modules/batch"

  name       = "my-batch-ec2"
  vpc_id     = "vpc-12345678"
  subnet_ids = ["subnet-12345678", "subnet-87654321"]

  compute_environment_type = "EC2"
  enable_spot              = true
  spot_bid_percentage      = 80
  instance_types           = ["m5.large", "m5.xlarge"]

  max_vcpus     = 512
  desired_vcpus = 128
  min_vcpus     = 0

  allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"

  tags = {
    Environment = "production"
    Project     = "my-project"
  }
}
```

### Using Existing IAM Roles

```hcl
module "batch" {
  source = "./modules/batch"

  name       = "my-batch"
  vpc_id     = "vpc-12345678"
  subnet_ids = ["subnet-12345678", "subnet-87654321"]

  create_iam_roles                = false
  batch_service_role_arn          = "arn:aws:iam::123456789012:role/existing-batch-role"
  ecs_task_execution_role_arn     = "arn:aws:iam::123456789012:role/existing-ecs-task-role"

  tags = {
    Environment = "production"
  }
}
```

## Requirements

| Name      | Version |
| --------- | ------- |
| terraform | >= 1.0  |
| aws       | >= 4.0  |

## Providers

| Name | Version |
| ---- | ------- |
| aws  | >= 4.0  |

## Resources Created

- `aws_batch_compute_environment` - Managed compute environment
- `aws_batch_job_queue` - Job queue
- `aws_security_group` - Security group (optional)
- `aws_iam_role` - IAM roles for Batch service, ECS task execution, and ECS instances (optional)
- `aws_iam_role_policy_attachment` - Policy attachments for IAM roles
- `aws_iam_instance_profile` - Instance profile for EC2 compute environments (optional)

## Inputs

| Name                        | Description                                                                    | Type           | Default                  | Required |
| --------------------------- | ------------------------------------------------------------------------------ | -------------- | ------------------------ | :------: |
| name                        | Name prefix for AWS Batch resources                                            | `string`       | n/a                      |   yes    |
| vpc_id                      | VPC ID where Batch resources will be created                                   | `string`       | n/a                      |   yes    |
| subnet_ids                  | List of subnet IDs for Batch compute environment                               | `list(string)` | n/a                      |   yes    |
| compute_environment_type    | Type of compute environment (EC2, FARGATE, or FARGATE_SPOT)                    | `string`       | `"FARGATE"`              |    no    |
| max_vcpus                   | Maximum number of vCPUs for the compute environment                            | `number`       | `256`                    |    no    |
| desired_vcpus               | Desired number of vCPUs for the compute environment                            | `number`       | `0`                      |    no    |
| min_vcpus                   | Minimum number of vCPUs for the compute environment                            | `number`       | `0`                      |    no    |
| instance_types              | List of instance types for EC2 compute environment                             | `list(string)` | `["optimal"]`            |    no    |
| allocation_strategy         | Allocation strategy (BEST_FIT_PROGRESSIVE, SPOT_CAPACITY_OPTIMIZED)            | `string`       | `"BEST_FIT_PROGRESSIVE"` |    no    |
| spot_bid_percentage         | Maximum percentage of on-demand price for spot instances                       | `number`       | `100`                    |    no    |
| enable_spot                 | Enable spot instances for EC2 compute environment                              | `bool`         | `false`                  |    no    |
| job_queue_priority          | Priority of the job queue                                                      | `number`       | `1`                      |    no    |
| job_queue_state             | State of the job queue (ENABLED or DISABLED)                                   | `string`       | `"ENABLED"`              |    no    |
| security_group_ids          | List of security group IDs to attach to compute environment                    | `list(string)` | `[]`                     |    no    |
| create_security_group       | Whether to create a security group for Batch                                   | `bool`         | `true`                   |    no    |
| allowed_cidr_blocks         | CIDR blocks allowed to access Batch resources                                  | `list(string)` | `[]`                     |    no    |
| create_iam_roles            | Whether to create IAM roles for Batch                                          | `bool`         | `true`                   |    no    |
| batch_service_role_arn      | ARN of existing IAM role for Batch service (if create_iam_roles is false)      | `string`       | `""`                     |    no    |
| ecs_instance_role_arn       | ARN of existing IAM role for ECS instances (if create_iam_roles is false)      | `string`       | `""`                     |    no    |
| ecs_task_execution_role_arn | ARN of existing IAM role for ECS task execution (if create_iam_roles is false) | `string`       | `""`                     |    no    |
| platform_version            | Platform version for Fargate compute environment                               | `string`       | `"LATEST"`               |    no    |
| tags                        | Tags to apply to all resources                                                 | `map(string)`  | `{}`                     |    no    |

## Outputs

| Name                        | Description                                             |
| --------------------------- | ------------------------------------------------------- |
| compute_environment_arn     | ARN of the AWS Batch compute environment                |
| compute_environment_name    | Name of the AWS Batch compute environment               |
| job_queue_arn               | ARN of the AWS Batch job queue                          |
| job_queue_name              | Name of the AWS Batch job queue                         |
| security_group_id           | ID of the security group created for Batch (if created) |
| batch_service_role_arn      | ARN of the IAM role for AWS Batch service               |
| ecs_task_execution_role_arn | ARN of the IAM role for ECS task execution              |
| ecs_instance_role_arn       | ARN of the IAM role for ECS instances (EC2 only)        |

## Notes

- For Fargate compute environments, instance types and allocation strategies are not applicable
- Spot instances are only supported for EC2 compute environments
- The module creates all necessary IAM roles by default, but you can provide existing roles
- Security groups allow all outbound traffic by default
- The compute environment is created in MANAGED mode with state ENABLED

## License

MIT
