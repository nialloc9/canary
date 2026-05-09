"""
Stage 4 - Value Rules
Analyzes dataset value constraints and validation rules using Claude QA Agent.
"""
import json
from agents.qa_agent.qa_agent import QAAgent
from ingestion.dependencies import Dependencies


class Stage4ValueRules(Dependencies):
    """
    Stage 4 analyzer for dataset value rules and constraints.
    
    Asks questions about:
    - Numeric column ranges and validity
    - Categorical column values
    - Date/time format and constraints
    - Format and pattern constraints
    """
    
    STAGE_4_QUESTIONS = [
        "For numeric columns: what is the valid min/max range? Are negative values ever valid?",
        "For categorical columns: what is the fixed set of allowed values? Can new values legitimately appear over time?",
        "For date/time columns: what format do you expect? Should dates always be recent, or can they be historical?",
        "Are there format or pattern constraints on any field? (email, phone, country code, regex pattern)",
    ]

    qa_agent = QAAgent()
    results = None
    
    def __init__(self, data_file_path: str, previous_results: dict = None):
        """
        Initialize Stage 4 analyzer.
        
        Args:
            data_file_path: Path to the CSV data file to analyze.
            previous_results: Results from previous stages for context.
        """
        self.data_file_path = data_file_path
        self.previous_results = previous_results or {}
        
    
    def analyze(self, use_batch: bool = True) -> list[dict]:
        """
        Perform Stage 4 analysis on the dataset.
        
        Args:
            use_batch: If True, uses batch processing (more efficient).
                      If False, processes questions individually.
        
        Returns:
            List of dictionaries with 'question' and 'answer' keys.
        """
        self.logger.info("="*70)
        self.logger.info("STAGE 4 - VALUE RULES ANALYSIS")
        self.logger.info("="*70)
        
        # Load the data
        self.qa_agent.load_data(self.data_file_path)
        
        # Build context string from previous stages
        context = self._build_context_string()
        
        # Ask questions
        self.logger.info("Analyzing dataset value rules and constraints...")
        self.logger.info("-" * 70)
        
        if use_batch:
            self.results = self.qa_agent.answer_questions_batch(self.STAGE_4_QUESTIONS, additional_context=context)
        else:
            self.results = self.qa_agent.answer_questions(self.STAGE_4_QUESTIONS, additional_context=context)
        
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
            Dictionary with keys: numeric_ranges, categorical_values, datetime_format, pattern_constraints
        """
        if self.results is None:
            raise ValueError("No results available. Run analyze() first.")
        
        return {
            "numeric_ranges": self.results[0]["answer"],
            "categorical_values": self.results[1]["answer"],
            "datetime_format": self.results[2]["answer"],
            "pattern_constraints": self.results[3]["answer"],
        }
