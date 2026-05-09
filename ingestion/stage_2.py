"""
Stage 2 - Schema & Structure
Analyzes dataset schema, column structure, and data types using Claude QA Agent.
"""
import json
from agents.qa_agent.qa_agent import QAAgent
from ingestion.dependencies import Dependencies


class Stage2SchemaStructure(Dependencies):
    """
    Stage 2 analyzer for dataset schema and structure information.
    
    Asks questions about:
    - Column flexibility and mutability
    - Data types for each column
    - Null/empty value handling and constraints
    - Data classification and sensitivity
    """
    
    STAGE_2_QUESTIONS = [
        "Are these columns fixed, or can new columns appear over time? Are any optional?",
        "For each column, what data type do you expect? (string, integer, float, date, boolean…)",
        "Which columns must always have a value? Which are allowed to be null or empty?",
        "What is the data classification or sensitivity level of this dataset? (e.g., public, internal, confidential, restricted, PII)",
    ]

    qa_agent = QAAgent()
    results = None
    
    def __init__(self, data_file_path: str, previous_results: dict = None):
        """
        Initialize Stage 2 analyzer.
        
        Args:
            data_file_path: Path to the CSV data file to analyze.
            previous_results: Results from previous stages for context.
        """
        self.data_file_path = data_file_path
        self.previous_results = previous_results or {}
        
    
    def analyze(self, use_batch: bool = True) -> list[dict]:
        """
        Perform Stage 2 analysis on the dataset.
        
        Args:
            use_batch: If True, uses batch processing (more efficient).
                      If False, processes questions individually.
        
        Returns:
            List of dictionaries with 'question' and 'answer' keys.
        """
        self.logger.info("="*70)
        self.logger.info("STAGE 2 - SCHEMA & STRUCTURE ANALYSIS")
        self.logger.info("="*70)
        
        # Load the data
        self.qa_agent.load_data(self.data_file_path)
        
        # Build context string from previous stages
        context = self._build_context_string()
        
        # Ask questions
        self.logger.info("Analyzing dataset schema and structure...")
        self.logger.info("-" * 70)
        
        if use_batch:
            self.results = self.qa_agent.answer_questions_batch(self.STAGE_2_QUESTIONS, additional_context=context)
        else:
            self.results = self.qa_agent.answer_questions(self.STAGE_2_QUESTIONS, additional_context=context)
        
        return self.results
    
    def _build_context_string(self) -> str:
        """
        Build context string from previous stages, including questions and answers.
        
        Returns:
            Formatted context string or empty string if no previous results.
        """
        if not self.previous_results:
            return ""
        
        context_parts = []
        for stage_name, stage_data in self.previous_results.items():
            context_parts.append(f"\n{stage_name}:")
            # stage_data is a list of dicts with 'question' and 'answer' keys
            if isinstance(stage_data, list):
                for idx, item in enumerate(stage_data, 1):
                    question = item.get("question", "")
                    answer = item.get("answer", "")
                    # Truncate long values for readability
                    q_str = question[:150] + "..." if len(question) > 150 else question
                    a_str = answer[:150] + "..." if len(answer) > 150 else answer
                    context_parts.append(f"  Q{idx}: {q_str}")
                    context_parts.append(f"  A{idx}: {a_str}")
        
        return "\n".join(context_parts)
    
    def get_results_dict(self) -> dict:
        """
        Get results as a structured dictionary.
        
        Returns:
            Dictionary with keys: column_flexibility, data_types, null_constraints, data_classification
        """
        if self.results is None:
            raise ValueError("No results available. Run analyze() first.")
        
        return {
            "column_flexibility": self.results[0]["answer"],
            "data_types": self.results[1]["answer"],
            "null_constraints": self.results[2]["answer"],
            "data_classification": self.results[3]["answer"],
        }
