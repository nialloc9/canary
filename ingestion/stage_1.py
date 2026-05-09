"""Stage 1 - Data Identity
Analyzes dataset identity, purpose, frequency, and origin using Claude QA Agent.
"""
import json
from agents.qa_agent.qa_agent import QAAgent
from ingestion.dependencies import Dependencies

class Stage1DataIdentity(Dependencies):
    """
    Stage 1 analyzer for dataset identity information.
    
    Asks questions about:
    - Dataset purpose and description
    - Data arrival frequency
    - Data source and origin
    """
    
    QUESTIONS = [
        "What does this dataset represent? Describe its purpose in one or two sentences.",
        "How often does this data arrive? (real-time, hourly, daily, ad hoc)",
        "What is the source system or origin of this data?",
    ]

    qa_agent = QAAgent()
    results = None
    
    def __init__(self, data_file_path: str, previous_results: dict = None):
        """
        Initialize Stage 1 analyzer.
        
        Args:
            data_file_path: Path to the CSV data file to analyze.
            previous_results: Results from previous stages for context.
        """
        self.data_file_path = data_file_path
        self.previous_results = previous_results or {}
        
    
    def analyze(self, use_batch: bool = True) -> list[dict]:
        """
        Perform Stage 1 analysis on the dataset.
        
        Args:
            use_batch: If True, uses batch processing (more efficient).
                      If False, processes questions individually.
        
        Returns:
            List of dictionaries with 'question' and 'answer' keys.
        """
        self.logger.info("="*70)
        self.logger.info("STAGE 1 - DATA IDENTITY ANALYSIS")
        self.logger.info("="*70)
        
        # Load the data
        self.qa_agent.load_data(self.data_file_path)
        
        # Build context string from previous stages
        context = self._build_context_string()
        
        # Ask questions
        self.logger.info("Analyzing dataset identity...")
        self.logger.info("-" * 70)
        
        if use_batch:
            self.results = self.qa_agent.answer_questions_batch(self.QUESTIONS, additional_context=context)
        else:
            self.results = self.qa_agent.answer_questions(self.QUESTIONS, additional_context=context)
        
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
            Dictionary with keys: dataset_purpose, data_frequency, data_source
        """
        if self.results is None:
            raise ValueError("No results available. Run analyze() first.")
        
        return {
            "dataset_purpose": self.results[0]["answer"],
            "data_frequency": self.results[1]["answer"],
            "data_source": self.results[2]["answer"],
        }
