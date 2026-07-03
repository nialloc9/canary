# ---- base ----
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- deps ----
FROM base AS deps
RUN apt-get update && apt-get install -y --no-install-recommends git curl unzip && rm -rf /var/lib/apt/lists/*

# Terraform + Terragrunt CLIs — used to `plan` generated infra before opening PRs
# (see app/tools/terraform/verify.py). Pinned versions, architecture-aware.
ARG TERRAFORM_VERSION=1.9.8
ARG TERRAGRUNT_VERSION=0.67.4
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${ARCH}.zip" \
    && unzip -q /tmp/terraform.zip -d /usr/local/bin \
    && rm /tmp/terraform.zip \
    && curl -fsSL -o /usr/local/bin/terragrunt "https://github.com/gruntwork-io/terragrunt/releases/download/v${TERRAGRUNT_VERSION}/terragrunt_linux_${ARCH}" \
    && chmod +x /usr/local/bin/terraform /usr/local/bin/terragrunt \
    && terraform version && terragrunt --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- dev ----
# Hot-reload via volume mount; source is NOT baked in
FROM deps AS dev
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ---- prod ----
FROM deps AS prod
COPY . .
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
