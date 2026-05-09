"""
Example usage of the Claude QA Agent
"""

from qa_agent import QAAgent
import json


def main():
    """Demonstrate the QA Agent."""
    
    # Initialize the agent
    agent = QAAgent()
    
    # Load the sample data
    agent.load_data("sample_data.csv")
    
    # Define questions to ask
    questions = [
        "What is the average age of all people in the data?",
        "How many people work in technology-related fields?",
        "Which city has the most people in the dataset?",
        "Who is the oldest person and what is their occupation?",
        "List all the unique cities in the data.",
    ]
    
    print("\n" + "="*60)
    print("ASKING QUESTIONS WITH QA AGENT")
    print("="*60)
    
    # Get answers using batch processing (more efficient)
    results = agent.answer_questions_batch(questions)
    
    # Display results
    print("\nResults:")
    print("-" * 60)
    for item in results:
        print(f"\nQ: {item['question']}")
        print(f"A: {item['answer']}")
    
    # Optionally save to JSON
    output_file = "qa_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Results saved to {output_file}")


if __name__ == "__main__":
    main()
