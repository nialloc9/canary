# dbt deploy pipeline — deliberately CI-tool-agnostic. Call these targets
# from whichever CI system runs this repo (GitHub Actions, CircleCI,
# anything else), or locally; nothing here assumes a specific CI provider.
#
# Every target runs dbt inside the pinned image built from docker/Dockerfile
# rather than whatever dbt happens to be on $PATH, so results are
# reproducible regardless of where this runs.
#
# Connection config is entirely environment-driven (see profiles.yml) — set
# these as secrets in your CI system, never commit them:
#   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY,
#   SNOWFLAKE_ROLE, SNOWFLAKE_DATABASE, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_SCHEMA

IMAGE := dbt-analytics

DBT_ENV := \
	-e SNOWFLAKE_ACCOUNT \
	-e SNOWFLAKE_USER \
	-e SNOWFLAKE_PRIVATE_KEY \
	-e SNOWFLAKE_ROLE \
	-e SNOWFLAKE_DATABASE \
	-e SNOWFLAKE_WAREHOUSE \
	-e SNOWFLAKE_SCHEMA

DBT_RUN := docker run --rm $(DBT_ENV) $(IMAGE)

.PHONY: build predeploy deploy postdeploy

build:
	docker build -f docker/Dockerfile -t $(IMAGE) .

# Install package dependencies and verify the Snowflake connection before
# anything runs against real tables.
predeploy: build
	$(DBT_RUN) deps
	$(DBT_RUN) debug

# Materialize every model.
deploy: build
	$(DBT_RUN) run

# Run tests and regenerate docs against what was just deployed.
postdeploy: build
	$(DBT_RUN) test
	$(DBT_RUN) docs generate
