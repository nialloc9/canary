# Pinned, reproducible environment for running dbt commands — the Makefile
# runs every target inside this image rather than whatever dbt happens to be
# on $PATH, so predeploy/deploy/postdeploy behave the same in CI as they do
# locally, regardless of which CI system is calling them.
FROM python:3.11-slim

RUN pip install --no-cache-dir dbt-snowflake==1.8.*

WORKDIR /dbt
COPY . .

ENTRYPOINT ["dbt"]
CMD ["--help"]
