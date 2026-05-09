import os
from typing import Optional

class Settings:
    """
    Central settings class for the Data Analysis Tool.
    
    Loads configuration from environment variables with sensible defaults.
    Supports development, staging, and production environments.
    """

    DEV_SETTINGS = {
        "ENV": os.getenv("ENV", "development"),
        "DEBUG": os.getenv("DEBUG", "True").lower() in ("true", "1", "yes"),
        "APP_NAME": "Data Analysis Tool",
        "APP_VERSION": "1.0.0",
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "ANTHROPIC_API_BASE_URL": os.getenv("ANTHROPIC_API_BASE_URL", "https://api.anthropic.com"),
        "ANTHROPIC_CLAUDE_MODEL": os.getenv("ANTHROPIC_CLAUDE_MODEL", "claude-sonnet-4-6"),
        "ANTHROPIC_CLAUDE_MAX_TOKENS": int(os.getenv("ANTHROPIC_CLAUDE_MAX_TOKENS", "4096")),
        "ANTHROPIC_CLAUDE_TEMPERATURE": float(os.getenv("ANTHROPIC_CLAUDE_TEMPERATURE", "0.7")),
    }

    PROD_SETTINGS = DEV_SETTINGS.copy() | {
        "DEBUG": False,
    }

    def get(self, key: str) -> Optional[str]:
        if os.getenv("ENV", "development") == "production":
            return self.PROD_SETTINGS.get(key)
        
        return self.DEV_SETTINGS.get(key)