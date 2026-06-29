SHELL := /bin/bash

SCRIPT := ./git.sh

.PHONY: help feature release hotfix sync commit dev-release

help:
	@echo "Gitflow Make Targets"
	@echo "  make feature NAME=my-feature        # create feature/<name> from develop"
	@echo "  make release                         # create release/YYYY-MM-DD-HH-MM-SS from develop"
	@echo "  make hotfix NAME=1.4.1-critical-fix  # create hotfix/<name> from main"
	@echo "  make sync                            # merge latest develop into current branch"
	@echo "  make commit                          # interactive commit and push"
	@echo "  make dev-release                     # push current branch and print PR URL"

feature:
	@if [[ -z "$(NAME)" ]]; then echo "Error: NAME is required. Example: make feature NAME=my-feature"; exit 1; fi
	@source "$(SCRIPT)" && create_feature_branch "$(NAME)"

release:
	@source "$(SCRIPT)" && create_release

hotfix:
	@if [[ -z "$(NAME)" ]]; then echo "Error: NAME is required. Example: make hotfix NAME=1.4.1-critical-fix"; exit 1; fi
	@source "$(SCRIPT)" && create_hotfix_branch "$(NAME)"

sync:
	@source "$(SCRIPT)" && sync_current_branch_with_default

commit:
	@source "$(SCRIPT)" && create_commit

dev-release:
	@source "$(SCRIPT)" && create_dev_release