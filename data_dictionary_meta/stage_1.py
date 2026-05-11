from agents.data_dictionary_agent.data_dictionary_agent import DataDictionaryAgent
from data_dictionary_meta.dependencies import Dependencies


class Stage1DataDictionary(Dependencies):

    data_dictionary_agent = DataDictionaryAgent()
    results = None

    def __init__(self, data_file_path: str, additional_context: dict = None):
        self.data_file_path = data_file_path
        self.additional_context = additional_context or {}

    def analyze(self) -> list[dict]:
        self.logger.info("=" * 70)
        self.logger.info("STAGE 1 - DATA DICTIONARY ANALYSIS")
        self.logger.info("=" * 70)

        self.data_dictionary_agent.load_data(self.data_file_path)
        self.results = self.data_dictionary_agent.generate(
            additional_context=self._build_context_string()
        )
        return self.results

    def _build_context_string(self) -> str:
        if not self.additional_context:
            return ""

        parts = []
        for stage_name, stage_data in self.additional_context.items():
            parts.append(f"\n{stage_name}:")
            if isinstance(stage_data, dict):
                for key, value in stage_data.items():
                    parts.append(f"  {key}: {value}")

        return "\n".join(parts)

    def get_results_dict(self) -> dict:
        if self.results is None:
            raise ValueError("No results available. Run analyze() first.")

        return {entry["column_name"]: entry for entry in self.results}
