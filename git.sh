DEVELOP_BRANCH=${DEVELOP_BRANCH:-develop}
MAIN_BRANCH=${MAIN_BRANCH:-main}

function ensure_git_repository() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not inside a git repository."
    return 1
  fi
}

function get_project_name() {
  local repository_path
  repository_path=$(get_repository_path_from_origin_remote)
  basename "$repository_path"
}

function get_repository_path_from_origin_remote() {
  local remote_url repository_path

  remote_url=$(git config --get remote.origin.url)
  if [[ -z "$remote_url" ]]; then
    echo "Error: remote.origin.url is not configured."
    return 1
  fi

  repository_path=$(echo "$remote_url" | sed -E 's#^(git@|ssh://git@|https?://)([^/:]+)[:/]##; s#\.git$##')

  if [[ "$repository_path" == "$remote_url" || -z "$repository_path" ]]; then
    echo "Error: Unable to parse repository path from remote URL: $remote_url"
    return 1
  fi

  echo "$repository_path"
}

function get_github_host_from_origin_remote() {
  local remote_url github_host

  remote_url=$(git config --get remote.origin.url)
  if [[ -z "$remote_url" ]]; then
    echo "Error: remote.origin.url is not configured."
    return 1
  fi

  github_host=$(echo "$remote_url" | sed -E 's#^(git@|ssh://git@|https?://)([^/:]+).*#\2#')
  if [[ -z "$github_host" || "$github_host" == "$remote_url" ]]; then
    echo "Error: Unable to parse GitHub host from remote URL: $remote_url"
    return 1
  fi

  echo "$github_host"
}

function push_branch_and_print_pr_url() {
  local branch_name github_host repository_path
  branch_name=$(git branch --show-current)
  github_host=$(get_github_host_from_origin_remote) || return 1
  repository_path=$(get_repository_path_from_origin_remote) || return 1

  git push --set-upstream origin "$branch_name"
  echo "Create PR: https://$github_host/$repository_path/pull/new/$branch_name"
}

function checkout_and_update_branch() {
  local base_branch="$1"
  git checkout "$base_branch" || return 1
  git pull origin "$base_branch" || return 1
}

function prompt_for_branch_suffix() {
  local provided_suffix="$1"

  if [[ -n "$provided_suffix" ]]; then
    echo "$provided_suffix"
    return 0
  fi

  echo -n "Enter branch name: "
  read -r provided_suffix
  echo "$provided_suffix"
}

function create_gitflow_branch() {
  local branch_prefix="$1"
  local base_branch="$2"
  local suffix="$3"
  local full_branch_name

  ensure_git_repository || return 1

  suffix=$(prompt_for_branch_suffix "$suffix")
  if [[ -z "$suffix" ]]; then
    echo "Error: Branch name cannot be empty."
    return 1
  fi

  full_branch_name="$branch_prefix/$suffix"
  echo "Creating $full_branch_name from $base_branch"

  checkout_and_update_branch "$base_branch" || return 1
  git checkout -b "$full_branch_name" || return 1
  git push -u origin "$full_branch_name"
}

function create_feature_branch() {
  create_gitflow_branch "feature" "$DEVELOP_BRANCH" "$1"
}

function create_hotfix_branch() {
  create_gitflow_branch "hotfix" "$MAIN_BRANCH" "$1"
}

function get_next_release_branch_name() {
  echo "release/$(date +%Y-%m-%d-%H-%M-%S)"
}

function create_release() {
  local release_branch

  ensure_git_repository || return 1
  release_branch=$(get_next_release_branch_name) || return 1

  echo "Creating $release_branch from $DEVELOP_BRANCH"
  checkout_and_update_branch "$DEVELOP_BRANCH" || return 1
  git checkout -b "$release_branch" || return 1
  git push -u origin "$release_branch"
}

function sync_current_branch_with_default() {
  local current_branch

  ensure_git_repository || return 1
  current_branch=$(git branch --show-current)

  checkout_and_update_branch "$DEVELOP_BRANCH" || return 1
  git checkout "$current_branch" || return 1
  git merge "$DEVELOP_BRANCH"

  echo "Updated $current_branch with latest changes from $DEVELOP_BRANCH"
}

function create_commit() {
  local commit_type commit_message

  ensure_git_repository || return 1

  echo -n "Enter commit type (feat, fix, refactor, docs, chore, none): "
  read -r commit_type
  if [[ "$commit_type" == "none" ]]; then
    return 0
  fi

  if [[ "$commit_type" != "feat" && "$commit_type" != "fix" && "$commit_type" != "refactor" && "$commit_type" != "docs" && "$commit_type" != "chore" ]]; then
    echo "Invalid type. Please use one of 'feat', 'fix', 'refactor', 'docs', 'chore'."
    return 1
  fi

  sync_current_branch_with_default || return 1

  echo -n "Enter commit message: "
  read -r commit_message

  git add .
  git commit -m "${commit_type}: ${commit_message}"
  git push
}

function create_dev_release() {
  ensure_git_repository || return 1
  push_branch_and_print_pr_url
}