resource "random_string" "random_string" {
  length  = 5
  special = false
  upper   = false
}



###############################################################################
# S3 Bucket – target data bucket
###############################################################################

resource "aws_s3_bucket" "data" {
  count  = local.create_bucket ? 1 : 0
  bucket = local.unique_name
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "data" {
  count  = local.create_bucket ? 1 : 0
  bucket = aws_s3_bucket.data[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  count  = local.create_bucket ? 1 : 0
  bucket = aws_s3_bucket.data[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
      kms_master_key_id = var.kms_key_arn != "" ? var.kms_key_arn : null
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  count                   = local.create_bucket ? 1 : 0
  bucket                  = aws_s3_bucket.data[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  count  = local.create_bucket ? 1 : 0
  bucket = aws_s3_bucket.data[0].id

  rule {
    id     = "data-lifecycle"
    status = "Enabled"

    dynamic "transition" {
      for_each = var.transition_to_ia_days > 0 ? [1] : []
      content {
        days          = var.transition_to_ia_days
        storage_class = "STANDARD_IA"
      }
    }

    dynamic "transition" {
      for_each = var.transition_to_glacier_days > 0 ? [1] : []
      content {
        days          = var.transition_to_glacier_days
        storage_class = "GLACIER"
      }
    }

    dynamic "expiration" {
      for_each = var.expiration_days > 0 ? [1] : []
      content {
        days = var.expiration_days
      }
    }
  }
}

###############################################################################
# IAM User with Access Keys (optional)
###############################################################################

resource "aws_iam_user" "s3" {
  count = var.create_access_keys ? 1 : 0
  name  = "${local.unique_name}-s3-user"
  tags  = local.tags
}

resource "aws_iam_user_policy" "s3" {
  count = var.create_access_keys ? 1 : 0
  name  = "${local.unique_name}-s3-rw"
  user  = aws_iam_user.s3[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          local.bucket_arn,
          "${local.bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_access_key" "s3" {
  count = var.create_access_keys ? 1 : 0
  user  = aws_iam_user.s3[0].name
}

resource "aws_secretsmanager_secret" "access_keys" {
  count = var.create_access_keys ? 1 : 0
  name  = "${var.project_name}/${local.unique_name}-s3-access-keys"
  tags  = local.tags
}

resource "aws_secretsmanager_secret_version" "access_keys" {
  count     = var.create_access_keys ? 1 : 0
  secret_id = aws_secretsmanager_secret.access_keys[0].id
  secret_string = jsonencode({
    access_key_id     = aws_iam_access_key.s3[0].id
    secret_access_key = aws_iam_access_key.s3[0].secret
  })
}

