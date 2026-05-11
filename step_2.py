"""
Data Dictionary Tool
Runs data dictionary analysis using Claude AI.
"""

import sys, json
from pathlib import Path
from data_dictionary_meta.data_dictionary_meta import DataDictionaryMeta
from utils.logger import Logger

logger = Logger("APP")


def main():
    """Main entry point for the data dictionary tool."""
    Logger.setup()
    logger.info("=" * 60)
    logger.info("Data Dictionary Analysis Tool")
    logger.info("=" * 60)

    while True:
        try:
            # file_path_input = input("\nEnter the path to your CSV file (or 'quit' to exit): ").strip()
            file_path_input = "./sample_data.csv"

            if file_path_input.lower() == 'quit':
                logger.info("Exiting...")
                sys.exit(0)

            if not file_path_input:
                logger.error("Please provide a valid file path.")
                continue

            file_path = Path(file_path_input)
            if not file_path.exists():
                logger.error(f"File '{file_path_input}' not found. Please check the path and try again.")
                continue

            # additional_context_file_path = input("\nEnter the path to your additional context JSON file (or 'quit' to exit): ").strip()
            additional_context_file_path = "./data_source_meta.json"
            additional_context = {}

            if additional_context_file_path.lower() != 'quit' and additional_context_file_path:
                additional_context_file = Path(additional_context_file_path)
                if additional_context_file.exists():
                    with open(additional_context_file, "r") as f:
                        additional_context = json.load(f)
                else:
                    logger.error(f"File '{additional_context_file_path}' not found. Continuing without additional context.")

            logger.info(f"Starting analysis on '{file_path_input}'...")
            app = DataDictionaryMeta(str(file_path), additional_context=additional_context)
            app.run_all_stages()

            logger.info("=" * 60)
            logger.info("Analysis Complete!")
            logger.info("=" * 60)
            app.display_combined_results()

            show_menu(app)

        except Exception as e:
            logger.exception(f"Unexpected error: {e}")


def show_menu(app):
    """Display menu for additional operations."""
    while True:
        logger.info("-" * 60)
        logger.info("Options: 1. Save results  2. Analyze another file  3. Exit")

        choice = input("\nSelect an option (1-3): ").strip()

        if choice == '1':
            app.save_combined_results()
            logger.info("Results saved!")
        elif choice == '2':
            break
        elif choice == '3':
            logger.info("Exiting...")
            sys.exit(0)
        else:
            logger.warning("Invalid option. Please select 1-3.")


if __name__ == "__main__":
    main()
