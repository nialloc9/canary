from ingestion.stage_1 import Stage1DataIdentity
from ingestion.stage_2 import Stage2SchemaStructure
from ingestion.stage_3 import Stage3VolumeCompleteness
from ingestion.stage_4 import Stage4ValueRules
from ingestion.stage_5 import Stage5UniquenessRelationships
from ingestion.stage_6 import Stage6SeverityBusinessLogic
from ingestion.stage_7 import Stage7AnythingElse
from ingestion.dependencies import Dependencies
import json


class Ingestion(Dependencies):
    """Main application class to run all stages of data analysis."""
    
    def __init__(self, data_file_path: str):
        """
        Initialize the application with the path to the data file.
        
        Args:
            data_file_path: Path to the CSV data file to analyze.
        """
        self.data_file_path = data_file_path
        self.combined_results = {}

    
    def run_all_stages(self):
        """Run all stages of analysis in sequence, passing context between stages."""
        self.logger.info("Starting comprehensive data analysis...")
        
        # Stage 1
        self.logger.info("Running Stage 1...")
        stage_1 = Stage1DataIdentity(self.data_file_path)
        stage_1.analyze()
        stage_1_raw_results = stage_1.results  # Get raw results with questions
        stage_1_results = stage_1.get_results_dict()
        self.combined_results["stage_1_data_identity"] = stage_1_results
        
        # Stage 2 (receives Stage 1 results with questions)
        self.logger.info("Running Stage 2...")
        stage_2 = Stage2SchemaStructure(
            self.data_file_path, 
            previous_results={"stage_1": stage_1_raw_results}
        )
        stage_2.analyze()
        stage_2_raw_results = stage_2.results
        stage_2_results = stage_2.get_results_dict()
        self.combined_results["stage_2_schema_structure"] = stage_2_results
        
        # Stage 3 (receives Stage 1-2 results with questions)
        self.logger.info("Running Stage 3...")
        stage_3 = Stage3VolumeCompleteness(
            self.data_file_path,
            previous_results={"stage_1": stage_1_raw_results, "stage_2": stage_2_raw_results}
        )
        stage_3.analyze()
        stage_3_raw_results = stage_3.results
        stage_3_results = stage_3.get_results_dict()
        self.combined_results["stage_3_volume_completeness"] = stage_3_results
        
        # Stage 4 (receives Stage 1-3 results with questions)
        self.logger.info("Running Stage 4...")
        stage_4 = Stage4ValueRules(
            self.data_file_path,
            previous_results={
                "stage_1": stage_1_raw_results, 
                "stage_2": stage_2_raw_results,
                "stage_3": stage_3_raw_results
            }
        )
        stage_4.analyze()
        stage_4_raw_results = stage_4.results
        stage_4_results = stage_4.get_results_dict()
        self.combined_results["stage_4_value_rules"] = stage_4_results
        
        # Stage 5 (receives Stage 1-4 results with questions)
        self.logger.info("Running Stage 5...")
        stage_5 = Stage5UniquenessRelationships(
            self.data_file_path,
            previous_results={
                "stage_1": stage_1_raw_results, 
                "stage_2": stage_2_raw_results,
                "stage_3": stage_3_raw_results,
                "stage_4": stage_4_raw_results
            }
        )
        stage_5.analyze()
        stage_5_raw_results = stage_5.results
        stage_5_results = stage_5.get_results_dict()
        self.combined_results["stage_5_uniqueness_relationships"] = stage_5_results
        
        # Stage 6 (receives Stage 1-5 results with questions)
        self.logger.info("Running Stage 6...")
        stage_6 = Stage6SeverityBusinessLogic(
            self.data_file_path,
            previous_results={
                "stage_1": stage_1_raw_results, 
                "stage_2": stage_2_raw_results,
                "stage_3": stage_3_raw_results,
                "stage_4": stage_4_raw_results,
                "stage_5": stage_5_raw_results
            }
        )
        stage_6.analyze()
        stage_6_raw_results = stage_6.results
        stage_6_results = stage_6.get_results_dict()
        self.combined_results["stage_6_severity_business_logic"] = stage_6_results
        
        # Stage 7 (receives Stage 1-6 results with questions)
        self.logger.info("Running Stage 7...")
        stage_7 = Stage7AnythingElse(
            self.data_file_path,
            previous_results={
                "stage_1": stage_1_raw_results, 
                "stage_2": stage_2_raw_results,
                "stage_3": stage_3_raw_results,
                "stage_4": stage_4_raw_results,
                "stage_5": stage_5_raw_results,
                "stage_6": stage_6_raw_results
            }
        )
        stage_7.analyze()
        stage_7_results = stage_7.get_results_dict()
        self.combined_results["stage_7_anything_else"] = stage_7_results
        
        self.logger.info("All stages completed successfully!")
    
    
    def get_combined_results(self) -> dict:
        """
        Get combined results from all stages in a single dictionary.
        
        Returns:
            Dictionary with all stage results organized by stage name.
        """
        return self.combined_results
    
    def save_combined_results(self, output_file: str = "analysis_results.json") -> None:
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
        self.logger.info("COMBINED DATA ANALYSIS RESULTS")
        self.logger.info("="*70)
        
        for stage_name, stage_results in self.combined_results.items():
            self.logger.info(f"\n{stage_name.upper().replace('_', ' ')}:")
            self.logger.info("-" * 70)
            for key, value in stage_results.items():
                self.logger.info(f"\n  {key.replace('_', ' ').title()}:")
                self.logger.info(f"  {value}")
        
        self.logger.info("\n" + "="*70) 
  
