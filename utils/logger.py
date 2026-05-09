"""Reusable logger for application."""

import logging


class Logger:
    """Centralized logging utility with common methods.

    Provides a reusable logger instance with common debugging, info, warning,
    and error logging methods.
    """

    def __init__(self, name: str = "APP") -> None:
        """Initialize logger with specified name.

        Args:
            name: Logger name (typically module or package name).
        """
        self._logger = logging.getLogger(name)

    @staticmethod
    def setup(log_level: str = "INFO") -> None:
        """Configure logging for the application.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message.

        Args:
            message: Message to log.
            **kwargs: Additional context to include.
        """
        self._logger.debug(message, extra=kwargs if kwargs else None)

    def info(self, message: str, **kwargs) -> None:
        """Log info message.

        Args:
            message: Message to log.
            **kwargs: Additional context to include.
        """
        self._logger.info(message, extra=kwargs if kwargs else None)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message.

        Args:
            message: Message to log.
            **kwargs: Additional context to include.
        """
        self._logger.warning(message, extra=kwargs if kwargs else None)

    def error(self, message: str, **kwargs) -> None:
        """Log error message.

        Args:
            message: Message to log.
            **kwargs: Additional context to include.
        """
        self._logger.error(message, extra=kwargs if kwargs else None)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message.

        Args:
            message: Message to log.
            **kwargs: Additional context to include.
        """
        self._logger.critical(message, extra=kwargs if kwargs else None)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback.

        Args:
            message: Message to log.
            **kwargs: Additional context to include.
        """
        self._logger.exception(message, extra=kwargs if kwargs else None)

    def set_level(self, level: str) -> None:
        """Change logging level at runtime.

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        self._logger.setLevel(level)
