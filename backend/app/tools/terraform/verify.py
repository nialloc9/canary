import asyncio
import base64
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services.llm_client import LLMClient
from app.models.stack import Stack

MAX_ATTEMPTS = 3
PLAN_TIMEOUT_SECONDS = 300

_FIX_PROMPT = """\
You are fixing a Terragrunt/Terraform configuration that failed `plan`.

Error output:
{error}

Current files:
{files}

Return ONLY a JSON object mapping each file path (relative to the stack directory) that needs \
a change to its full corrected content, e.g. {{"path/to/file.hcl": "new content"}}. Only include \
files you are actually changing. If you cannot determine a fix from the error, return {{}}. \
Return nothing else — no markdown fences, no explanation.
"""


@dataclass
class VerificationResult:
    ok: bool
    attempts: int
    log: str


def _stack_env(stack: Stack) -> dict:
    env = dict(os.environ)
    env.update({
        "SNOWFLAKE_ORGANIZATION_NAME": stack.sf_organization_name or "",
        "SNOWFLAKE_ACCOUNT_NAME": stack.sf_account_name or "",
        "SNOWFLAKE_USER": stack.sf_user or "",
        "SNOWFLAKE_AUTHENTICATOR": "jwt",
        "AWS_ACCESS_KEY_ID": stack.cloud_access_key_id or "",
        "AWS_SECRET_ACCESS_KEY": stack.cloud_secret_access_key or "",
        "AWS_DEFAULT_REGION": stack.cloud_region or "us-east-1",
    })
    if stack.sf_private_key_b64:
        env["SNOWFLAKE_PRIVATE_KEY"] = base64.b64decode(stack.sf_private_key_b64).decode("utf-8")
    return env


def _run(args: list[str], cwd: Path, env: dict) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True, text=True, timeout=PLAN_TIMEOUT_SECONDS
        )
        return result.returncode == 0, (result.stdout + result.stderr)
    except subprocess.TimeoutExpired as exc:
        return False, f"Timed out after {PLAN_TIMEOUT_SECONDS}s running {' '.join(args)}: {exc}"


async def _run_commands(
    stack_dir: Path, env: dict, init_cmd: list[str], plan_cmd: list[str]
) -> tuple[bool, str]:
    def _sync() -> tuple[bool, str]:
        ok, log = _run(init_cmd, stack_dir, env)
        if not ok:
            return False, log
        return _run(plan_cmd, stack_dir, env)

    return await asyncio.to_thread(_sync)


async def _attempt_fix(stack_dir: Path, error_output: str, file_glob: str) -> bool:
    """Ask Claude to patch the generated config files based on the plan error.

    Only files matching `file_glob` under the stack's own generated directory are
    in scope — vendored terraform modules live in a sibling `modules/` directory
    and are never touched. Returns True if any file was changed (worth retrying).
    """
    files = {
        str(path.relative_to(stack_dir)): path.read_text()
        for path in stack_dir.rglob(file_glob)
    }
    if not files:
        return False

    files_blob = "\n\n".join(f"=== {name} ===\n{content}" for name, content in files.items())
    prompt = _FIX_PROMPT.format(error=error_output[-6000:], files=files_blob)

    text = await LLMClient().complete(prompt, max_tokens=4096)
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        patch = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not patch:
        return False

    changed = False
    for rel_path, content in patch.items():
        target = (stack_dir / rel_path).resolve()
        if not target.is_relative_to(stack_dir.resolve()):
            continue  # guard against path traversal in the model's response
        target.write_text(content)
        changed = True
    return changed


async def _verify_plan(
    stack_dir: Path,
    stack: Stack,
    init_cmd: list[str],
    plan_cmd: list[str],
    file_glob: str,
    max_attempts: int,
) -> VerificationResult:
    env = _stack_env(stack)
    log = ""

    for attempt in range(1, max_attempts + 1):
        ok, log = await _run_commands(stack_dir, env, init_cmd, plan_cmd)
        if ok:
            return VerificationResult(ok=True, attempts=attempt, log=log)

        if attempt == max_attempts:
            return VerificationResult(ok=False, attempts=attempt, log=log)

        fixed = await _attempt_fix(stack_dir, log, file_glob)
        if not fixed:
            return VerificationResult(ok=False, attempts=attempt, log=log)

    return VerificationResult(ok=False, attempts=max_attempts, log=log)


async def verify_stack_plan(stack_dir: Path, stack: Stack, max_attempts: int = MAX_ATTEMPTS) -> VerificationResult:
    """Run `terragrunt plan` for a stack's generated landing-zone directory,
    asking Claude to patch and retry on failure, up to `max_attempts` times."""
    return await _verify_plan(
        stack_dir,
        stack,
        init_cmd=["terragrunt", "run-all", "init", "--terragrunt-non-interactive"],
        plan_cmd=["terragrunt", "run-all", "plan", "--terragrunt-non-interactive"],
        file_glob="*.hcl",
        max_attempts=max_attempts,
    )


async def verify_bootstrap_plan(stack_dir: Path, stack: Stack, max_attempts: int = MAX_ATTEMPTS) -> VerificationResult:
    """Verify a stack's plain-Terraform state-backend bootstrap files.

    No remote backend / Terragrunt involved here — these files are what *create*
    the S3 bucket + DynamoDB table that everything else later uses as its backend,
    so they must plan against purely local state.
    """
    return await _verify_plan(
        stack_dir,
        stack,
        init_cmd=["terraform", "init"],
        plan_cmd=["terraform", "plan"],
        file_glob="*.tf",
        max_attempts=max_attempts,
    )
