"""
Claude QA Agent - Reads data files and answers questions using Claude API
"""

import json
from pathlib import Path
from typing import Optional
import anthropic
import pandas as pd
from agents.qa_agent.dependencies import Dependencies
from settings import Settings

class QAAgent(Dependencies):
    """Agent that uses Claude to answer questions about data files."""
    
    settings = Settings()
    data_context = None

    def __init__(self):
        """
        Initialize the QA Agent.
        
        Args:
            api_key: Optional Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
            logger: Optional Logger instance. If not provided, creates a new one.
        """
        self.logger.info("Initializing QA Agent")
        self.client = anthropic.Anthropic(api_key=self.settings.get("ANTHROPIC_API_KEY"))
        self.model = self.settings.get("ANTHROPIC_CLAUDE_MODEL")
        self.logger.debug(f"QA Agent initialized with model: {self.model}")
        
    def load_data(self, file_path: str) -> None:
        """
        Load data from a CSV file.
        
        Args:
            file_path: Path to the CSV file to load.
        """
        self.logger.debug(f"Attempting to load data from: {file_path}")
        
        file_path = Path(file_path)
        if not file_path.exists():
            self.logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() != '.csv':
            self.logger.error(f"Unsupported file type: {file_path.suffix}")
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

        df = pd.read_csv(file_path)
        self.data_context = df.sample(n=min(100, len(df)), random_state=42)
        self.logger.info(f"✓ Loaded data from {file_path}")
        self.logger.info(f"  Rows: {len(self.data_context)}/{len(df)}")
        self.logger.info(f"  Columns: {list(self.data_context.columns)}")
    
    def answer_questions(self, questions: list[str], additional_context: Optional[str] = None) -> list[dict]:
        """
        Answer a list of questions based on the loaded data.
        
        Args:
            questions: List of questions to answer.
            additional_context: Optional additional context to include in the prompt.
            
        Returns:
            List of dictionaries with 'question' and 'answer' keys.
        """
        if self.data_context is None:
            raise ValueError("No data loaded. Call load_data() first.")
        
        # Convert data to string format for context
        data_string = self.data_context.to_string()
        
        results = []
        
        for question in questions:
            answer = self._get_answer(question, data_string, additional_context)
            results.append({
                "question": question,
                "answer": answer
            })
        
        return results
    
    def _get_answer(self, question: str, data_string: str, additional_context: Optional[str] = None) -> str:
        """
        Get an answer to a single question from the QA Agent.
        
        Args:
            question: The question to answer.
            data_string: The data context as a string.
            additional_context: Optional additional context to include in the prompt.
            
        Returns:
            The answer from the QA Agent.
        """
        # Build the prompt with optional additional context
        prompt = f"""You are a data analysis assistant. Answer questions about the data below.
Keep answers short (1-2 sentences maximum). No preamble, no explanation — facts only.

Data:
{data_string}"""

        if additional_context:
            prompt += f"\n\nAdditional Context:\n{additional_context}"

        prompt += f"\n\nQuestion: {question}\n\nAnswer (1-2 sentences, facts only):"
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        return message.content[0].text
    
    def answer_questions_batch(self, questions: list[str], additional_context: Optional[str] = None) -> list[dict]:
        """
        Answer multiple questions in a single API call for efficiency.
        
        Args:
            questions: List of questions to answer.
            additional_context: Optional additional context to include in the prompt.
            
        Returns:
            List of dictionaries with 'question' and 'answer' keys.
        """
        if self.data_context is None:
            raise ValueError("No data loaded. Call load_data() first.")
        
        data_string = self.data_context.to_string()
        
        # Format questions for the prompt
        questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        
        # Build the prompt with optional additional context
        prompt = f"""You are a data analysis assistant. Answer questions about the data below.
Keep each answer short (1-2 sentences maximum). No preamble, no explanation — facts only.

Data:
{data_string}"""

        if additional_context:
            prompt += f"\n\nAdditional Context:\n{additional_context}"

        prompt += f"""\n\nQuestions:
{questions_text}

Return ONLY a JSON array. Each element must have "question" and "answer" keys. Answers must be 1-2 sentences, facts only.
[
  {{"question": "Question 1?", "answer": "Answer 1"}},
  {{"question": "Question 2?", "answer": "Answer 2"}}
]"""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        response_text = message.content[0].text
        
        # Parse the JSON response
        try:
            # Handle potential markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            results = json.loads(response_text)
            return results
        except json.JSONDecodeError:
            # Fallback to individual question answering if batch fails
            self.logger.warning("Could not parse batch response, falling back to individual questions.")
            return self.answer_questions(questions, additional_context)
