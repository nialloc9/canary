from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import Project
from app.models.stack import Stack, StackStateBackend
from app.schemas.stack import (
    StackCreate,
    StackUpdate,
    StackOut,
    WarehouseUpdate,
    WarehouseOut,
    CloudUpdate,
    CloudOut,
    ReorderRequest,
    ConnectionTestResult,
    TopologyOut,
    TopologyNodeOut,
    TopologyEdgeOut,
    TopologySkippedOut,
    AccessKeysOut,
)
from app.services.topology_service import get_stack_topology
from app.services.aws_secrets_service import get_landing_zone_access_keys

router = APIRouter(prefix="/stacks", tags=["stacks"])


def _stack_out(record: Stack) -> StackOut:
    return StackOut(
        id=record.id,
        name=record.name,
        verify_before_pr=record.verify_before_pr,
        verify_max_attempts=record.verify_max_attempts,
        circleci_context=record.circleci_context,
        sort_order=record.sort_order,
        is_default=record.is_default,
        warehouse=WarehouseOut(
            type=record.type,
            organization_name=record.sf_organization_name or "",
            account_name=record.sf_account_name or "",
            user=record.sf_user or "",
            authenticator=record.sf_authenticator,
            private_key_b64="••••••••" if record.sf_private_key_b64 else None,
            database=record.sf_database,
            schema_=record.sf_schema,
            warehouse=record.sf_warehouse,
            role=record.sf_role,
        ),
        cloud=CloudOut(
            provider=record.cloud_provider,
            access_key_id=record.cloud_access_key_id or "",
            secret_access_key="••••••••" if record.cloud_secret_access_key else None,
            region=record.cloud_region or "us-east-1",
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _apply_warehouse(record: Stack, warehouse: WarehouseUpdate | None) -> None:
    if warehouse is None:
        return
    if warehouse.type is not None:
        record.type = warehouse.type
    if warehouse.organization_name is not None:
        record.sf_organization_name = warehouse.organization_name
    if warehouse.account_name is not None:
        record.sf_account_name = warehouse.account_name
    if warehouse.user is not None:
        record.sf_user = warehouse.user
    if warehouse.authenticator is not None:
        record.sf_authenticator = warehouse.authenticator
    if warehouse.database is not None:
        record.sf_database = warehouse.database
    if warehouse.schema_ is not None:
        record.sf_schema = warehouse.schema_
    if warehouse.warehouse is not None:
        record.sf_warehouse = warehouse.warehouse
    if warehouse.role is not None:
        record.sf_role = warehouse.role
    if warehouse.private_key_b64 and not warehouse.private_key_b64.startswith("••"):
        record.sf_private_key_b64 = warehouse.private_key_b64


def _apply_cloud(record: Stack, cloud: CloudUpdate | None) -> None:
    if cloud is None:
        return
    if cloud.provider is not None:
        record.cloud_provider = cloud.provider
    if cloud.access_key_id is not None:
        record.cloud_access_key_id = cloud.access_key_id
    if cloud.region is not None:
        record.cloud_region = cloud.region
    if cloud.secret_access_key and not cloud.secret_access_key.startswith("••"):
        record.cloud_secret_access_key = cloud.secret_access_key


async def _get_stack_or_404(db: AsyncSession, account_id: str, stack_id: str) -> Stack:
    result = await db.execute(
        select(Stack).where(Stack.account_id == account_id, Stack.id == stack_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Stack not found")
    return record


@router.get("", response_model=list[StackOut])
async def list_stacks(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(Stack).where(Stack.account_id == account_id).order_by(Stack.sort_order)
    )
    return [_stack_out(r) for r in result.scalars().all()]


@router.post("", response_model=StackOut, status_code=201)
async def create_stack(
    payload: StackCreate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    existing = await db.execute(
        select(Stack).where(Stack.account_id == account_id, Stack.name == payload.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A stack with this name already exists")

    result = await db.execute(
        select(func.coalesce(func.max(Stack.sort_order), -1)).where(Stack.account_id == account_id)
    )
    next_sort_order = result.scalar_one() + 1

    record = Stack(
        account_id=account_id,
        name=payload.name,
        verify_before_pr=payload.verify_before_pr or False,
        verify_max_attempts=payload.verify_max_attempts or 3,
        circleci_context=payload.circleci_context,
        sort_order=next_sort_order,
        is_default=False,
    )
    _apply_warehouse(record, payload.warehouse)
    _apply_cloud(record, payload.cloud)
    db.add(record)
    await db.flush()
    return _stack_out(record)


@router.put("/reorder", response_model=list[StackOut])
async def reorder_stacks(
    payload: ReorderRequest,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(Stack).where(Stack.account_id == account_id))
    stacks_by_id = {r.id: r for r in result.scalars().all()}

    if set(payload.stack_ids) != set(stacks_by_id.keys()):
        raise HTTPException(status_code=400, detail="stack_ids must include every existing stack exactly once")

    # Bump into a disjoint range first to avoid unique(account_id, sort_order) collisions mid-update.
    offset = len(stacks_by_id)
    for record in stacks_by_id.values():
        record.sort_order += offset
    await db.flush()

    for index, stack_id in enumerate(payload.stack_ids):
        stacks_by_id[stack_id].sort_order = index
    await db.flush()

    result = await db.execute(
        select(Stack).where(Stack.account_id == account_id).order_by(Stack.sort_order)
    )
    return [_stack_out(r) for r in result.scalars().all()]


@router.put("/{stack_id}", response_model=StackOut)
async def update_stack(
    stack_id: str,
    payload: StackUpdate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_stack_or_404(db, account_id, stack_id)

    if payload.name is not None and payload.name != record.name:
        existing = await db.execute(
            select(Stack).where(Stack.account_id == account_id, Stack.name == payload.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A stack with this name already exists")
        record.name = payload.name

    if payload.verify_before_pr is not None:
        record.verify_before_pr = payload.verify_before_pr

    if payload.verify_max_attempts is not None:
        record.verify_max_attempts = payload.verify_max_attempts

    if payload.circleci_context is not None:
        record.circleci_context = payload.circleci_context

    _apply_warehouse(record, payload.warehouse)
    _apply_cloud(record, payload.cloud)

    await db.flush()
    return _stack_out(record)


@router.delete("/{stack_id}", status_code=204)
async def delete_stack(
    stack_id: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_stack_or_404(db, account_id, stack_id)

    count_result = await db.execute(
        select(func.count()).select_from(Stack).where(Stack.account_id == account_id)
    )
    if count_result.scalar_one() <= 1:
        raise HTTPException(status_code=409, detail="Cannot delete the last remaining stack")

    state_backend_result = await db.execute(
        select(func.count()).select_from(StackStateBackend).where(StackStateBackend.stack_id == stack_id)
    )
    if state_backend_result.scalar_one() > 0:
        raise HTTPException(
            status_code=409,
            detail="This stack has already been bootstrapped and cannot be deleted",
        )

    await db.delete(record)


@router.post("/{stack_id}/test", response_model=ConnectionTestResult)
async def test_stack_connection(
    stack_id: str,
    payload: StackUpdate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_stack_or_404(db, account_id, stack_id)
    wh = payload.warehouse

    organization_name = (
        wh.organization_name if wh and wh.organization_name is not None else None
    ) or record.sf_organization_name
    account_name = (wh.account_name if wh and wh.account_name is not None else None) or record.sf_account_name
    # snowflake-connector-python takes a single `account` string, not separate org/account
    # fields — for the current org-account identifier format that string must be
    # "<organization>-<account>". Legacy locator identifiers (e.g. "xy12345.us-east-1")
    # already contain the full routing info and don't take an org prefix.
    account = (
        f"{organization_name}-{account_name}"
        if organization_name and account_name and "." not in account_name
        else account_name
    )
    user = (wh.user if wh and wh.user is not None else None) or record.sf_user
    database = (wh.database if wh and wh.database is not None else None) or record.sf_database
    schema_ = (wh.schema_ if wh and wh.schema_ is not None else None) or record.sf_schema
    warehouse = (wh.warehouse if wh and wh.warehouse is not None else None) or record.sf_warehouse
    role = (wh.role if wh and wh.role is not None else None) or record.sf_role
    private_key_b64 = (
        wh.private_key_b64
        if wh and wh.private_key_b64 and not wh.private_key_b64.startswith("••")
        else record.sf_private_key_b64
    )

    try:
        import snowflake.connector  # type: ignore
        import base64, tempfile, os

        kwargs: dict = {"account": account, "user": user}
        if database:
            kwargs["database"] = database
        if schema_:
            kwargs["schema"] = schema_
        if warehouse:
            kwargs["warehouse"] = warehouse
        if role:
            kwargs["role"] = role

        if not private_key_b64:
            return ConnectionTestResult(ok=False, message="No private key configured for this stack")

        pem = base64.b64decode(private_key_b64)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".p8") as f:
            f.write(pem)
            key_path = f.name
        try:
            kwargs["authenticator"] = "snowflake_jwt"
            kwargs["private_key_file"] = key_path
            conn = snowflake.connector.connect(**kwargs)
            conn.close()
        finally:
            os.unlink(key_path)

        return ConnectionTestResult(ok=True, message="Connection successful")
    except ImportError:
        return ConnectionTestResult(ok=False, message="snowflake-connector-python not installed")
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=str(exc))


@router.post("/{stack_id}/test-cloud", response_model=ConnectionTestResult)
async def test_stack_cloud_connection(
    stack_id: str,
    payload: StackUpdate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_stack_or_404(db, account_id, stack_id)
    cl = payload.cloud

    access_key_id = (cl.access_key_id if cl and cl.access_key_id is not None else None) or record.cloud_access_key_id
    region = (cl.region if cl and cl.region is not None else None) or record.cloud_region or "us-east-1"
    secret_access_key = (
        cl.secret_access_key
        if cl and cl.secret_access_key and not cl.secret_access_key.startswith("••")
        else record.cloud_secret_access_key
    )

    if not access_key_id or not secret_access_key:
        return ConnectionTestResult(ok=False, message="Access key ID and secret access key are required")

    try:
        import boto3  # type: ignore
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore

        client = boto3.client(
            "sts",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        identity = client.get_caller_identity()
        return ConnectionTestResult(
            ok=True,
            message=f"Connected as {identity['Arn']} (account {identity['Account']})",
        )
    except ImportError:
        return ConnectionTestResult(ok=False, message="boto3 not installed")
    except (ClientError, BotoCoreError) as exc:
        return ConnectionTestResult(ok=False, message=str(exc))
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=str(exc))


@router.get("/{stack_id}/topology", response_model=TopologyOut)
async def get_topology(
    stack_id: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_stack_or_404(db, account_id, stack_id)
    topology = await get_stack_topology(db, account_id, record, force_refresh=refresh)
    return TopologyOut(
        nodes=[TopologyNodeOut(**asdict(n)) for n in topology.nodes],
        edges=[TopologyEdgeOut(**asdict(e)) for e in topology.edges],
        fetched_at=datetime.fromtimestamp(topology.fetched_at, tz=timezone.utc),
        connected=topology.connected,
        error=topology.error,
        skipped=[TopologySkippedOut(**asdict(s)) for s in topology.skipped],
    )


@router.get("/{stack_id}/landing-zones/{landing_zone_name}/access-keys", response_model=AccessKeysOut)
async def get_landing_zone_access_keys_route(
    stack_id: str,
    landing_zone_name: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_stack_or_404(db, account_id, stack_id)
    project_result = await db.execute(select(Project).where(Project.account_id == account_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="No project found for this account.")

    keys = await get_landing_zone_access_keys(record, project.name, landing_zone_name)
    if keys is None:
        raise HTTPException(
            status_code=404,
            detail="Access keys not available yet — the landing zone's PR needs to be merged and applied first.",
        )
    return AccessKeysOut(**keys)
