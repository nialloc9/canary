"""
Data Analysis Tool
Runs comprehensive 7-stage data analysis using Claude AI.
"""

import sys
from pathlib import Path
from data_source_meta.data_source_meta import DataSourceMeta


def main():
    """Main entry point for the data analysis tool."""
    print("=" * 60)
    print("Comprehensive Data Analysis Tool (7-Stage Framework)")
    print("=" * 60)
    
    while True:
        try:
            # Prompt user for file path
            file_path_input = input("\nEnter the path to your CSV file (or 'quit' to exit): ").strip()
            
            if file_path_input.lower() == 'quit':
                print("Exiting...")
                sys.exit(0)
            
            if not file_path_input:
                print("Error: Please provide a valid file path.")
                continue
            
            # Verify file exists
            file_path = Path(file_path_input)
            if not file_path.exists():
                print(f"Error: File '{file_path_input}' not found. Please check the path and try again.")
                continue
            
            # Run the analysis
            print(f"\n✓ Starting analysis on '{file_path_input}'...")
            app = DataSourceMeta(str(file_path))
            app.run_all_stages()
            
            # Display results
            print("\n" + "=" * 60)
            print("Analysis Complete!")
            print("=" * 60)
            app.display_combined_results()
            
            # Option to save or analyze another file
            show_menu(app)
            
        except Exception as e:
            print(f"Error: {str(e)}")


def show_menu(app):
    """Display menu for additional operations."""
    while True:
        print("\n" + "-" * 60)
        print("Options:")
        print("1. Save results to file")
        print("2. Analyze another file")
        print("3. Exit")
        
        choice = input("\nSelect an option (1-3): ").strip()
        
        if choice == '1':
            app.save_combined_results()
            print("✓ Results saved!")
        elif choice == '2':
            break
        elif choice == '3':
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid option. Please select 1-3.")


if __name__ == "__main__":
    main()
