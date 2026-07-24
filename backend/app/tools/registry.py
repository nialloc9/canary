from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from app.tools.terraform.s3 import LandingZoneTool
from app.tools.terraform.snowflake_pipe import SnowflakePipeTool
from app.tools.terraform.update import UpdateLandingZoneTool
from app.tools.terraform.remove import RemoveTerragruntBlockTool
from app.tools.terraform.blocks import ListTerragruntBlocksTool, ReadTerragruntBlockTool, EditTerragruntBlockTool
from app.tools.terraform.status import CheckDeployedInfrastructureTool
from app.tools.terraform.access_keys import GetLandingZoneAccessKeysTool
from app.tools.dbt.staging_model import CreateDbtStagingModelTool


class ToolRegistry:
    def __init__(self, db: AsyncSession, account_id: str):
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults(db, account_id)

    def _register_defaults(self, db: AsyncSession, account_id: str) -> None:
        self.register(LandingZoneTool(db, account_id))
        self.register(UpdateLandingZoneTool(db, account_id))
        self.register(RemoveTerragruntBlockTool(db, account_id))
        self.register(ListTerragruntBlocksTool(db, account_id))
        self.register(ReadTerragruntBlockTool(db, account_id))
        self.register(EditTerragruntBlockTool(db, account_id))
        self.register(SnowflakePipeTool(db, account_id))
        self.register(CheckDeployedInfrastructureTool(db, account_id))
        self.register(GetLandingZoneAccessKeysTool(db, account_id))
        self.register(CreateDbtStagingModelTool(db, account_id))

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_tool_specs(self) -> list[dict]:
        return [t.to_tool_spec() for t in self.all()]
