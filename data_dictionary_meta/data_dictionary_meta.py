from data_dictionary_meta.stage_1 import Stage1DataDictionary
from data_dictionary_meta.dependencies import Dependencies
import json


class DataDictionaryMeta(Dependencies):
    """Main application class to run all stages of data dictionary analysis."""
    
    def __init__(self, data_file_path: str, additional_context: dict = None):
        """
        Initialize the application with the path to the data file.
        
        Args:
            data_file_path: Path to the CSV data file to analyze.
            additional_context: Optional dictionary with additional context for analysis.
        """
        self.data_file_path = data_file_path
        self.additional_context = additional_context or {}
        self.combined_results = {}

    
    def run_all_stages(self):
        """Run all stages of analysis in sequence, passing context between stages."""
        self.logger.info("Starting comprehensive data dictionary analysis...")
        
        # Stage 1
        self.logger.info("Running Stage 1...")
        stage_1 = Stage1DataDictionary(self.data_file_path, self.additional_context)
        stage_1.analyze()
        stage_1_results = stage_1.get_results_dict()
        self.combined_results["stage_1_data_dictionary"] = stage_1_results
        
        self.logger.info("All stages completed successfully!")


    
    def get_combined_results(self) -> dict:
        """
        Get combined results from all stages in a single dictionary.
        
        Returns:
            Dictionary with all stage results organized by stage name.
        """
        return self.combined_results
    
    def save_combined_results(self, output_file: str = "data_dictionary_meta.json") -> None:
        """
        Save combined results from all stages to a JSON file.
        
        Args:
            output_file: Path to save the JSON results.
        """
        with open(output_file, "w") as f:
            json.dump(self.combined_results, f, indent=2)
        self.logger.info(f"Combined results saved to {output_file}")
    
    def display_combined_results(self) -> None:
        """Display combined results in a formatted manner."""
        self.logger.info("\n" + "="*70)
        self.logger.info("COMBINED DATA DICTIONARY ANALYSIS RESULTS")
        self.logger.info("="*70)
        
        for stage_name, stage_results in self.combined_results.items():
            self.logger.info(f"\n{stage_name.upper().replace('_', ' ')}:")
            self.logger.info("-" * 70)
            for key, value in stage_results.items():
                self.logger.info(f"\n  {key.replace('_', ' ').title()}:")
                self.logger.info(f"  {value}")
        
        self.logger.info("\n" + "="*70) 
  
