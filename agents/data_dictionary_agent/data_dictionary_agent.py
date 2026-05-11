"""
Data Dictionary Agent - Generates a structured data dictionary from a CSV file using Claude.
"""

import json
from pathlib import Path
from typing import Optional
import anthropic
import pandas as pd
from agents.data_dictionary_agent.dependencies import Dependencies
from settings import Settings


class DataDictionaryAgent(Dependencies):
    """Agent that uses Claude to produce a data dictionary for a CSV dataset."""

    settings = Settings()
    _df: Optional[pd.DataFrame] = None

    def __init__(self):
        self.logger.info("Initializing Data Dictionary Agent")
        self.client = anthropic.Anthropic(api_key=self.settings.get("ANTHROPIC_API_KEY"))
        self.model = self.settings.get("ANTHROPIC_CLAUDE_MODEL")
        self.logger.debug(f"Data Dictionary Agent initialized with model: {self.model}")

    def load_data(self, file_path: str) -> None:
        """Load a CSV file ready for dictionary generation.

        Args:
            file_path: Path to the CSV file.
        """
        path = Path(file_path)
        if not path.exists():
            self.logger.error(f"File not found: {path}")
            raise FileNotFoundError(f"File not found: {path}")

        if path.suffix.lower() != ".csv":
            self.logger.error(f"Unsupported file type: {path.suffix}")
            raise ValueError(f"Unsupported file type: {path.suffix}")

        df = pd.read_csv(path)
        self._df = df.sample(n=min(100, len(df)), random_state=42)
        self.logger.info(f"Loaded {path} — sampled {len(self._df)}/{len(df)} rows, {len(self._df.columns)} columns")

    def generate(self, additional_context: Optional[str] = None) -> list[dict]:
        """Generate a data dictionary for the loaded dataset.

        Each entry in the returned list describes one column and contains:
            - column_name
            - data_type
            - description
            - example_values
            - nullable (bool)
            - unique (bool)
            - notes

        Args:
            additional_context: Optional domain knowledge or business context to
                                 include in the prompt so Claude can produce richer
                                 descriptions (e.g. upstream system docs, field
                                 naming conventions, business rules).

        Returns:
            List of dicts, one per column.
        """
        if self._df is None:
            raise ValueError("No data loaded. Call load_data() first.")

        schema_summary = self._build_schema_summary()
        prompt = self._build_prompt(schema_summary, additional_context)

        self.logger.debug(f"Calling {self.model} to generate data dictionary")
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.settings.get("ANTHROPIC_CLAUDE_MAX_TOKENS"),
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text
        self.logger.debug(f"Received response ({len(response_text)} characters)")

        dictionary = self._parse_response(response_text)
        self.logger.info(f"Data dictionary generated with {len(dictionary)} entries")
        return dictionary

    def save(self, dictionary: list[dict], output_file: str = "data_dictionary.json") -> None:
        """Save a generated dictionary to a JSON file.

        Args:
            dictionary: Output of generate().
            output_file: Destination path.
        """
        with open(output_file, "w") as f:
            json.dump(dictionary, f, indent=2)
        self.logger.info(f"Data dictionary saved to {output_file}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_schema_summary(self) -> str:
        """Build a compact schema + sample summary from the loaded DataFrame."""
        lines = []
        for col in self._df.columns:
            series = self._df[col]
            dtype = str(series.dtype)
            null_count = int(series.isna().sum())
            unique_count = int(series.nunique(dropna=True))
            samples = series.dropna().unique()[:5].tolist()
            lines.append(
                f"  {col}: dtype={dtype}, nulls={null_count}, "
                f"unique={unique_count}, samples={samples}"
            )
        return "\n".join(lines)

    def _build_prompt(self, schema_summary: str, additional_context: Optional[str]) -> str:
        prompt = f"""You are a data engineering assistant. Generate a data dictionary for the dataset described below.

Schema (column name, dtype, null count, unique count, sample values):
{schema_summary}"""

        if additional_context:
            prompt += f"\n\nAdditional Context:\n{additional_context}"

        prompt += """

Return ONLY a JSON array. Each element must describe one column with exactly these keys:
- "column_name": string
- "data_type": string (e.g. string, integer, float, boolean, date, email)
- "description": string — 1 sentence, what the field represents
- "example_values": array of up to 3 representative values
- "nullable": boolean
- "unique": boolean (true if every non-null value is distinct)
- "notes": string — any data quality issues, constraints, or business rules observed; empty string if none

No extra keys. No markdown. No explanation outside the JSON array."""

        return prompt

    def _parse_response(self, response_text: str) -> list[dict]:
        """Extract and parse the JSON array from the model response."""
        text = response_text.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse data dictionary response: {e}")
            raise ValueError(f"Model returned invalid JSON: {e}") from e
