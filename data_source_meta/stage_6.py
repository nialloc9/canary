"""
Stage 6 - Severity & Business Logic
Analyzes dataset severity levels and business logic using Claude QA Agent.
"""
import json
from agents.qa_agent.qa_agent import QAAgent
from data_source_meta.dependencies import Dependencies


class Stage6SeverityBusinessLogic(Dependencies):
    """
    Stage 6 analyzer for dataset severity and business logic.
    
    Asks questions about:
    - Critical columns and business impact
    - Known quirks and edge cases
    - Notification and response procedures
    """
    
    STAGE_6_QUESTIONS = [
        "If something looks wrong, which columns are most critical to the business? (helps prioritise alert severity)",
        "Are there any known quirks or edge cases in the data you'd want the system to tolerate rather than flag?",
        "What should happen when an anomaly is detected — who should be notified, and how urgently?",
    ]

    qa_agent = QAAgent()
    results = None
    
    def __init__(self, data_file_path: str, previous_results: dict = None):
        """
        Initialize Stage 6 analyzer.
        
        Args:
            data_file_path: Path to the CSV data file to analyze.
            previous_results: Results from previous stages for context.
        """
        self.data_file_path = data_file_path
        self.previous_results = previous_results or {}
        
    
    def analyze(self, use_batch: bool = True) -> list[dict]:
        """
        Perform Stage 6 analysis on the dataset.
        
        Args:
            use_batch: If True, uses batch processing (more efficient).
                      If False, processes questions individually.
        
        Returns:
            List of dictionaries with 'question' and 'answer' keys.
        """
        self.logger.info("="*70)
        self.logger.info("STAGE 6 - SEVERITY & BUSINESS LOGIC ANALYSIS")
        self.logger.info("="*70)
        
        # Load the data
        self.qa_agent.load_data(self.data_file_path)
        
        # Build context string from previous stages
        context = self._build_context_string()
        
        # Ask questions
        self.logger.info("Analyzing dataset severity and business logic...")
        self.logger.info("-" * 70)
        
        if use_batch:
            self.results = self.qa_agent.answer_questions_batch(self.STAGE_6_QUESTIONS, additional_context=context)
        else:
            self.results = self.qa_agent.answer_questions(self.STAGE_6_QUESTIONS, additional_context=context)
        
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
            Dictionary with keys: critical_columns, known_quirks, notification_procedure
        """
        if self.results is None:
            raise ValueError("No results available. Run analyze() first.")
        
        return {
            "critical_columns": self.results[0]["answer"],
            "known_quirks": self.results[1]["answer"],
            "notification_procedure": self.results[2]["answer"],
        }
