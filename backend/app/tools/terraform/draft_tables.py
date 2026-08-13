import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool
from app.services.data_profile_service import infer_profile


class DraftLandingZoneTablesTool(BaseTool):
    """Turns a loose, free-form description of one or more tables (the user
    dumping several pasted sample files and rough descriptions in one message,
    rather than answering create_landing_zone's one-table-at-a-time questions)
    into a structured draft — the same shape as create_landing_zone's `tables`
    argument — for the user to review/edit in a form before confirming.

    Pure inference: never touches Terraform, GitHub, or the database (unlike
    create_landing_zone, which persists a profile per table via
    infer_profile/upsert_profile), so it's safe to call speculatively — the
    same landing zone can be re-drafted as many times as the conversation
    needs before anything real gets created.
    """

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "draft_landing_zone_tables"

    @property
    def description(self) -> str:
        return (
            "Turn a loose, free-form description of one or more tables into a structured draft — "
            "inferring file format, size stats, description, and columns per table from its "
            "sample_files, the same way create_landing_zone does. Returns the enriched draft as "
            "JSON; a review form is rendered automatically from this tool's result, so after calling "
            "it just tell the user you've put together a draft below for them to review — don't "
            "restate every field back to them in prose, and don't call create_landing_zone yet, wait "
            "for their confirmed/edited tables to come back. "
            "Use this INSTEAD OF create_landing_zone's one-table-at-a-time questions whenever the "
            "user has already given you enough to work with in one go — e.g. pasted multiple sample "
            "files up front, or described several tables in one message. Split what they gave you "
            "into one entry per table yourself: best-guess a name for each table if they didn't give "
            "one explicitly (e.g. from a sample's filename or content) — the review form lets them "
            "fix anything you got wrong, including names. "
            "owner/refresh_rate/data_classification are extracted, never inferred: if the user states "
            "one anywhere in their message — even briefly, e.g. 'owner is data' or 'these refresh "
            "hourly' — carry it onto every table it plausibly applies to (a single blanket statement "
            "usually applies to all tables in the message, not just one); if they didn't say it, leave "
            "that field empty rather than guessing a plausible-sounding value — an invented value the "
            "user never said is worse than a blank one they still have to fill in, since a blank field "
            "is obviously incomplete but a wrong-looking-right one might get missed in review. "
            "If the user is describing just one table and answering questions one at a time, don't "
            "bother calling this — go straight to "
            "create_landing_zone as usual."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "landing_zone_name": {
                    "type": "string",
                    "description": "The landing zone/project name this is for, if known — used only "
                    "as extra context for inference, not persisted by this tool.",
                },
                "tables": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Best-guess table name — infer one from context/"
                                "filename if the user didn't give one explicitly.",
                            },
                            "description": {"type": "string"},
                            "owner": {
                                "type": "string",
                                "description": "Only if the user actually stated it (even briefly) — "
                                "leave omitted otherwise, never guess.",
                            },
                            "refresh_rate": {
                                "type": "string",
                                "description": "Only if the user actually stated it — leave omitted "
                                "otherwise, never guess.",
                            },
                            "data_classification": {
                                "type": "string",
                                "description": "Must match one of this account's configured "
                                "classifications (listed in your system context). Only set if the user "
                                "stated it or a sample column obviously demands it (e.g. an email "
                                "field) — leave omitted otherwise so it falls back to the account "
                                "default in the review form.",
                            },
                            "s3_prefix": {"type": "string"},
                            "file_format_type": {
                                "type": "string",
                                "enum": ["JSON", "CSV", "PARQUET", "AVRO", "ORC", "XML"],
                            },
                            "sample_files": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "filename": {"type": "string"},
                                        "content": {"type": "string"},
                                    },
                                    "required": ["content"],
                                },
                                "description": "Whatever sample content the user pasted for this "
                                "table, split out from their message. Omit if they gave none for "
                                "this table.",
                            },
                            "columns": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "type": {"type": "string"},
                                        "description": {"type": "string"},
                                        "example": {"type": "string"},
                                    },
                                    "required": ["name"],
                                },
                            },
                        },
                        "required": ["name"],
                    },
                    "description": "One entry per table you can identify in the user's message.",
                },
            },
            "required": ["tables"],
        }

    async def execute(self, tables: list[dict], landing_zone_name: str = "") -> str:
        if not tables:
            return "No tables to draft — ask the user to describe at least one table or paste a sample file."

        drafted = []
        for t in tables:
            table_name = t.get("name") or "table"
            sample_files = t.get("sample_files") or []
            entry = {
                "name": table_name,
                "owner": t.get("owner") or "",
                "refresh_rate": t.get("refresh_rate") or "",
                "data_classification": t.get("data_classification") or "",
                "s3_prefix": t.get("s3_prefix") or f"{table_name}/",
                "filter_suffix": "",
                "description": t.get("description") or "",
                "file_format_type": t.get("file_format_type") or "",
                "columns": t.get("columns") or [],
                "expected_size_bytes": None,
                "min_size_bytes": None,
                "max_size_bytes": None,
                "sample_files": sample_files,
            }
            if sample_files:
                profile = await infer_profile(
                    landing_zone_name=landing_zone_name or "draft",
                    table_name=table_name,
                    sample_files=sample_files,
                    data_description=t.get("description"),
                    file_format=t.get("file_format_type"),
                    columns=t.get("columns"),
                )
                entry["description"] = profile.get("description") or entry["description"]
                entry["file_format_type"] = profile.get("file_format") or entry["file_format_type"] or "JSON"
                entry["columns"] = profile.get("columns") or entry["columns"]
                entry["expected_size_bytes"] = profile.get("expected_size_bytes")
                entry["min_size_bytes"] = profile.get("min_size_bytes")
                entry["max_size_bytes"] = profile.get("max_size_bytes")
            drafted.append(entry)

        return json.dumps({"tables": drafted}, indent=2)
