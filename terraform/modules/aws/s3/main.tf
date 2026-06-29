resource "random_string" "random_string" {
  length  = 5
  special = false
  upper   = false
}

resource "aws_s3_bucket" "bucket" {
  bucket = local.unique_name

  force_destroy = var.force_destroy

  dynamic "server_side_encryption_configuration" {
    for_each = var.encrypt_at_rest ? [1] : []
    content {
      rule {
        apply_server_side_encryption_by_default {
          sse_algorithm = "AES256"
        }
      }
    }
  }

  dynamic "cors_rule" {
    for_each = var.cors_rules
    content {
      allowed_headers = cors_rule.value.allowed_headers
      allowed_methods = cors_rule.value.allowed_methods
      allowed_origins = cors_rule.value.allowed_origins
      expose_headers  = cors_rule.value.expose_headers
      max_age_seconds = cors_rule.value.max_age_seconds
    }
  }

  tags = local.tags
}


resource "aws_s3_bucket_versioning" "versioning_example" {
  bucket = aws_s3_bucket.bucket.id
  versioning_configuration {
    status = var.versioning 
  }
}

resource "aws_s3_bucket_public_access_block" "block" {
  bucket = aws_s3_bucket.bucket.id

  block_public_acls   = var.block_public_access
  block_public_policy = var.block_public_access
}

resource "aws_s3_bucket_policy" "public_bucket_policy" {
  bucket = aws_s3_bucket.bucket.bucket

  count = var.block_public_access || var.policy != "" ? 0 : 1

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action    = "s3:GetObject",
        Effect    = "Allow",
        Resource  = "${aws_s3_bucket.bucket.arn}/*",
        Principal = "*"
      }
    ]
  })

  depends_on = [aws_s3_bucket.bucket]
}

resource "aws_s3_bucket_policy" "custom_bucket_policy" {
  bucket = aws_s3_bucket.bucket.bucket

  count = var.policy == "" ? 0 : 1

  policy = var.policy

  depends_on = [aws_s3_bucket.bucket]
}