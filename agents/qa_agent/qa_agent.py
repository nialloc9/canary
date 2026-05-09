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
        
        if file_path.suffix.lower() == '.csv':
            self.logger.debug(f"Reading CSV file: {file_path}")
            self.data_context = pd.read_csv(file_path)
        else:
            self.logger.error(f"Unsupported file type: {file_path.suffix}")
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        self.logger.info(f"✓ Loaded data from {file_path}")
        self.logger.info(f"  Rows: {len(self.data_context)}")
        self.logger.info(f"  Columns: {list(self.data_context.columns)}")
    
    def answer_questions(self, questions: list[str], additional_context: Optional[str] = None) -> list[dict]:
        """
        Answer a list of questions based on the loaded data.
        
        Args:
            questions: List of questions to answer.
            additional_context: Optional additional context to include in the prompt.
        self.logger.debug(f"answer_questions called with {len(questions)} question(s)")
        
        if self.data_context is None:
            self.logger.error("No data loaded. Call load_data() first.")
            raise ValueError("No data loaded. Call load_data() first.")
        
        # Convert data to string format for context
        data_string = self.data_context.to_string()
        self.logger.debug(f"Data context prepared ({len(data_string)} characters)")
        
        results = []
        
        for i, question in enumerate(questions, 1):
            self.logger.debug(f"Processing question {i}/{len(questions)}: {question}")
            try:
                answer = self._get_answer(question, data_string, additional_context)
                results.append({
                    "question": question,
                    "answer": answer
                })
                self.logger.debug(f"Question {i} answered successfully")
            except Exception as e:
                self.logger.error(f"Error answering question {i}: {str(e)}")
                raise
        
        self.logger.info(f"Successfully answered {len(results)} question(s)")    results.append({
                "question": question,
                "answer": answer
            })
        
        return results
    
    def _get_answer(self, question: str, data_string: str, additional_context: Optional[str] = None) -> str:
        self.logger.debug(f"_get_answer called for: {question[:50]}...")
        
        # Build the prompt with optional additional context
        prompt = f"""You are a data analysis assistant. Based on the following data, answer the question concisely and accurately.

Data:
{data_string}"""
        
        if additional_context:
            prompt += f"\n\nAdditional Context:\n{additional_context}"
            self.logger.debug("Additional context included in prompt")
        
        prompt += f"\n\nQuestion: {question}\n\nProvide a clear, direct answer based on the data and context provided."
        
        try:
            self.logger.debug(f"Making API call to {self.model} with max_tokens=1024")
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
            
            answer = message.content[0].text
            self.logger.debug(f"Received answer from API ({len(answer)} characters)")
            return answer
        except Exception as e:
            self.logger.error(f"API call failed: {str(e)}")
            raise.create(
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
        self.logger.debug(f"answer_questions_batch called with {len(questions)} question(s)")
        
        if self.data_context is None:
            self.logger.error("No data loaded. Call load_data() first.")
            raise ValueError("No data loaded. Call load_data() first.")
        
        data_string = self.data_context.to_string()
        self.logger.debug(f"Data context prepared ({len(data_string)} characters)")
        
        # Format questions for the prompt
        questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        
        # Build the prompt with optional additional context
        prompt = f"""You are a data analysis assistant. Based on the following data, answer each question concisely and accurately.

Data:
{data_string}"""
        
        if additional_context:
            prompt += f"\n\nAdditional Context:\n{additional_context}"
            self.logger.debug("Additional context included in prompt")
        
        prompt += f"""\n\nQuestions:
{questions_text}

Provide answers as a JSON array of objects with "question" and "answer" keys. Example format:
[
  {{"question": "Question 1?", "answer": "Answer 1"}},
  {{"question": "Question 2?", "answer": "Answer 2"}}
]

Return ONLY the JSON array, no additional text."""
        
        try:
            self.logger.debug(f"Making batch API call to {self.model} with max_tokens=2048")
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
            self.logger.debug(f"Received batch response from API ({len(response_text)} characters)")
            
            # Parse the JSON response
            try:
                # Handle potential markdown code blocks
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                    self.logger.debug("Extracted JSON from markdown code block")
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                    self.logger.debug("Extracted JSON from code block")
                
                results = json.loads(response_text)
                self.logger.info(f"Successfully parsed batch response with {len(results)} answers")
                return results
            except json.JSONDecodeError as e:
                # Fallback to individual question answering if batch fails
                self.logger.warning(f"Could not parse batch response: {str(e)}. Falling back to individual questions.")
                return self.answer_questions(questions, additional_context)
        except Exception as e:
            self.logger.error(f"Batch API call failed: {str(e)}")
            raise
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            results = json.loads(response_text)
            return results
        except json.JSONDecodeError:
            # Fallback to individual question answering if batch fails
            self.logger.warning("Could not parse batch response, falling back to individual questions.")
            return self.answer_questions(questions, additional_context)
