# Canary

A CLI tool that performs comprehensive, AI-powered data quality analysis on CSV files using Claude. It runs a structured 7-stage pipeline, where each stage builds on the findings of the previous ones, and produces a combined JSON report of results.

## How it works

The tool ingests a CSV file and passes it through 7 sequential analysis stages, each powered by the Claude QA Agent:

| Stage | Name | What it analyses |
|-------|------|-----------------|
| 1 | Data Identity | Dataset purpose, arrival frequency, and source/origin |
| 2 | Schema & Structure | Column types, naming conventions, and schema validity |
| 3 | Volume & Completeness | Row counts, null rates, and missing data patterns |
| 4 | Value Rules | Data ranges, formats, and constraint violations |
| 5 | Uniqueness & Relationships | Duplicate detection and inter-column relationships |
| 6 | Severity & Business Logic | Business rule violations and severity classification |
| 7 | Catch-all | Any additional anomalies or concerns not covered above |

Results from each stage are passed as context into the next, allowing later stages to build a progressively richer understanding of the dataset.

## Prerequisites

- Python 3.11+
- An Anthropic API key

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file (or export variables in your shell) with the required environment variables listed below.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | — | Your Anthropic API key |
| `ENV` | No | `development` | Runtime environment (`development` / `production`) |
| `DEBUG` | No | `True` | Enable debug logging |
| `ANTHROPIC_API_BASE_URL` | No | `https://api.anthropic.com` | Anthropic API base URL |
| `ANTHROPIC_CLAUDE_MODEL` | No | `claude-sonnet-4-6` | Claude model ID to use |
| `ANTHROPIC_CLAUDE_MAX_TOKENS` | No | `4096` | Maximum tokens per response |
| `ANTHROPIC_CLAUDE_TEMPERATURE` | No | `0.7` | Sampling temperature |

Minimal `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
python main.py
```

You will be prompted to enter the path to a CSV file. After analysis completes you can save the results to `analysis_results.json` or analyse another file.

## Docker

```bash
docker compose up
```

Ensure your environment variables are set in a `.env` file at the project root before running.

## Output

Results are saved as `analysis_results.json` — a structured JSON object with one key per stage containing the questions asked and Claude's answers.
