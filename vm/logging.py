import os
import logging

LOGGING = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warnings": logging.WARNING,
    "error": logging.ERROR,
    "critial": logging.CRITICAL
}


def get_logger(config_file_path: str) -> logging.Logger:
    """ This function is resposible for logger initialization
        using configuration file.
    
        Args:
            config_file_path (str): The path to the configutation file, e.g. config.ini

        Returns:
            logging.Logger: The configured logger instance.
    """
    if os.path.exists(config_file_path):
        config = configparser.ConfigParser()
        config.read(config_file_path)
        level = config["logging"]["level"].lower()
        if level in LOGGING:
            logger = logging
            logger.basicConfig(level=level)
            return logger
        raise ValueError(f"Unknown logging level: {level}")
    raise ValueError("No configuration file was provided.")
