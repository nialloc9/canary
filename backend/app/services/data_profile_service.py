import json
import statistics

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_profile import LandingZoneDataProfile
from app.services.llm_client import LLMClient

_MAX_SAMPLE_CHARS_PER_FILE = 4000
_MAX_SAMPLES_IN_PROMPT = 5

_INFER_PROMPT = """\
You are looking at sample file(s) that will be landed raw into a Snowflake Bronze \
table (as a single VARIANT column) for a data pipeline named "{landing_zone_name}".

{description_hint}
{columns_hint}

Sample file(s):

{samples}

Return ONLY a JSON object with exactly these fields:
  description - a short (1-3 sentence) plain-language description of what this data represents
  columns - a list of objects, one per distinct field/column found across the samples, each with:
    name        - the field name
    type        - your best guess at its data type (e.g. string, integer, float, boolean, timestamp, array, object)
    description - a short plain-language description of what this field likely represents
    example     - a representative example value from the samples, as a string

Return ONLY valid JSON with no explanation or markdown fences.
"""


def _sniff_format(sample_files: list[dict]) -> str | None:
    """Best-effort guess at file_format_type from the first sample's filename
    extension, falling back to sniffing its content. Returns None (leave it to
    the caller's own default) if nothing matches."""
    first = sample_files[0]
    name = (first.get("filename") or "").lower()
    for ext, fmt in ((".json", "JSON"), (".csv", "CSV"), (".xml", "XML"), (".parquet", "PARQUET"), (".avro", "AVRO"), (".orc", "ORC")):
        if name.endswith(ext):
            return fmt

    content = (first.get("content") or "").strip()
    if content.startswith("{") or content.startswith("["):
        return "JSON"
    if content.startswith("<"):
        return "XML"
    lines = content.splitlines()
    if lines and "," in lines[0]:
        return "CSV"
    return None


def _size_stats(sample_files: list[dict]) -> tuple[int, int, int]:
    """(min, max, expected) byte size across the samples' own content length.
    These are only ever a starting point derived from what was provided —
    not a claim about the true range of files this landing zone will ever
    see — the caller should treat them as an editable default, not a fact."""
    sizes = [len(f["content"].encode("utf-8")) for f in sample_files]
    return min(sizes), max(sizes), round(statistics.mean(sizes))


async def infer_profile(
    landing_zone_name: str,
    sample_files: list[dict],
    data_description: str | None = None,
    file_format: str | None = None,
    expected_size_bytes: int | None = None,
    min_size_bytes: int | None = None,
    max_size_bytes: int | None = None,
    columns: list[dict] | None = None,
) -> dict:
    """Resolve a full data profile from whatever the user explicitly supplied,
    filling in everything else from the sample file(s). Deterministic where
    possible (size stats, format sniffing); the LLM is only used for the
    genuinely semantic parts (description, per-column meaning) and only when
    the user didn't already supply them."""
    inferred_min, inferred_max, inferred_expected = _size_stats(sample_files)
    resolved = {
        "file_format": file_format or _sniff_format(sample_files),
        "min_size_bytes": min_size_bytes if min_size_bytes is not None else inferred_min,
        "max_size_bytes": max_size_bytes if max_size_bytes is not None else inferred_max,
        "expected_size_bytes": expected_size_bytes if expected_size_bytes is not None else inferred_expected,
        "description": data_description,
        "columns": columns,
    }

    if resolved["description"] and resolved["columns"]:
        return resolved

    description_hint = (
        f'The user already described it as: "{data_description}" — use this verbatim, do not replace it.'
        if data_description else
        "The user did not provide a description — infer one from the samples."
    )
    columns_hint = (
        "The user already supplied column descriptions for some fields — still list every field you can "
        "see in the samples, filling in your own guess for any not already described."
        if columns else ""
    )
    samples_text = "\n\n".join(
        f"=== {f.get('filename', f'sample_{i}')} ===\n{f['content'][:_MAX_SAMPLE_CHARS_PER_FILE]}"
        for i, f in enumerate(sample_files[:_MAX_SAMPLES_IN_PROMPT])
    )
    prompt = _INFER_PROMPT.format(
        landing_zone_name=landing_zone_name,
        description_hint=description_hint,
        columns_hint=columns_hint,
        samples=samples_text,
    )

    llm = LLMClient()
    text = await llm.complete(prompt, max_tokens=2048)
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    inferred = json.loads(text)

    if not resolved["description"]:
        resolved["description"] = inferred.get("description")
    if not resolved["columns"]:
        resolved["columns"] = inferred.get("columns")

    return resolved


async def upsert_profile(
    db: AsyncSession, account_id: str, landing_zone_name: str, resolved: dict
) -> LandingZoneDataProfile:
    result = await db.execute(
        select(LandingZoneDataProfile).where(
            LandingZoneDataProfile.account_id == account_id,
            LandingZoneDataProfile.landing_zone_name == landing_zone_name,
        )
    )
    record = result.scalar_one_or_none()
    if record:
        record.file_format = resolved["file_format"]
        record.description = resolved["description"]
        record.expected_size_bytes = resolved["expected_size_bytes"]
        record.min_size_bytes = resolved["min_size_bytes"]
        record.max_size_bytes = resolved["max_size_bytes"]
        record.columns = resolved["columns"]
    else:
        record = LandingZoneDataProfile(
            account_id=account_id,
            landing_zone_name=landing_zone_name,
            file_format=resolved["file_format"],
            description=resolved["description"],
            expected_size_bytes=resolved["expected_size_bytes"],
            min_size_bytes=resolved["min_size_bytes"],
            max_size_bytes=resolved["max_size_bytes"],
            columns=resolved["columns"],
        )
        db.add(record)
    await db.flush()
    return record
