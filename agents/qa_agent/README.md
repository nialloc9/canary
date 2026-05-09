# Claude QA Agent

A Python agent that uses Claude AI to read data files and answer questions, returning results as a structured list of question-answer objects.

## Features

- **Load CSV Data**: Reads and parses CSV files into pandas DataFrames
- **Intelligent Q&A**: Uses Claude API to answer questions about your data
- **Batch Processing**: Efficiently processes multiple questions in a single API call
- **Structured Output**: Returns results as a JSON-compatible list of dictionaries with `question` and `answer` keys

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set your Anthropic API key as an environment variable:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Usage

### Basic Example

```python
from agents.claude_qa_agent import ClaudeQAAgent

# Initialize agent
agent = ClaudeQAAgent()

# Load your data file
agent.load_data("sample_data.csv")

# Define questions
questions = [
    "What is the average age?",
    "How many people are in technology?",
    "Which cities are represented?"
]

# Get answers (batch processing for efficiency)
results = agent.answer_questions_batch(questions)

# results is now a list of dicts:
# [
#   {"question": "What is the average age?", "answer": "..."},
#   {"question": "How many people are in technology?", "answer": "..."},
#   ...
# ]
```

### Using Individual Questions

For fine-grained control, use `answer_questions()` instead:

```python
results = agent.answer_questions(questions)
```

## API Reference

### `ClaudeQAAgent(api_key=None)`
Initialize the agent. If `api_key` is not provided, it uses the `ANTHROPIC_API_KEY` environment variable.

### `load_data(file_path)`
Load a CSV file to use as context for answering questions.

**Parameters:**
- `file_path` (str): Path to the CSV file

**Raises:**
- `FileNotFoundError`: If the file doesn't exist
- `ValueError`: If file type is not CSV

### `answer_questions_batch(questions)`
Answer multiple questions in a single API call (recommended for efficiency).

**Parameters:**
- `questions` (list[str]): List of questions to answer

**Returns:**
- `list[dict]`: List of objects with `question` and `answer` keys

### `answer_questions(questions)`
Answer questions individually (one API call per question).

**Parameters:**
- `questions` (list[str]): List of questions to answer

**Returns:**
- `list[dict]`: List of objects with `question` and `answer` keys

## Example Script

Run the example script to see the agent in action:

```bash
python agents/example_usage.py
```

This will:
1. Load the sample data
2. Ask predefined questions
3. Display the results
4. Save results to `qa_results.json`

## Response Format

All results are returned as a list of dictionaries:

```json
[
  {
    "question": "What is the average age?",
    "answer": "The average age is 33.5 years."
  },
  {
    "question": "How many people work in technology?",
    "answer": "4 people work in technology-related fields (Software Engineer, Product Manager, DevOps Engineer, and Systems Architect)."
  }
]
```

## Notes

- **Batch Processing**: Use `answer_questions_batch()` for better performance when asking multiple questions
- **API Costs**: Each question or batch costs Claude API tokens. Batch processing is more efficient
- **Data Format**: Currently supports CSV files. The agent converts data to a string representation for Claude context
- **API Model**: Uses Claude 3.5 Sonnet for optimal speed and accuracy
