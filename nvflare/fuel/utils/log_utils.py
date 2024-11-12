# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.import logging
import logging.config
import os
import json
import re
from logging import Logger
from logging.handlers import RotatingFileHandler

from nvflare.apis.workspace import Workspace

import logging


class ConsoleColors:
    GREY = "\x1b[38;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    BLUE = "\x1b[34;20m"
    RESET = "\x1b[0m"

LEVEL_COLORS = {
    "DEBUG": ConsoleColors.GREY,
    "INFO": ConsoleColors.GREY,
    "WARNING": ConsoleColors.YELLOW,
    "ERROR": ConsoleColors.RED,
    "CRITICAL": ConsoleColors.BOLD_RED,
}


class ShortNameFormatter(logging.Formatter):
    #def __init__(self, fmt="%(asctime)s - %(shortname)s - %(levelname)s - %(message)s", datefmt=None):
    def __init__(self, fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt=None, style="%"):
        fmt = fmt.replace("%(name)s", "%(shortname)s")
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record):
        # Replace 'name' with 'shortname' as the part after the last dot
        record.shortname = record.name.split('.')[-1]
        return super().format(record)


class ColorFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[34;20m"
    reset = "\x1b[0m"

    # Define the format as a string and use it in FORMATS
    default_format = "%(asctime)s - %(shortname)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: ConsoleColors.GREY + default_format + ConsoleColors.RESET,
        logging.INFO: ConsoleColors.GREY + default_format + ConsoleColors.RESET,
        logging.WARNING: ConsoleColors.YELLOW + default_format + ConsoleColors.RESET,
        logging.ERROR: ConsoleColors.RED + default_format + ConsoleColors.RESET,
        logging.CRITICAL: ConsoleColors.BOLD_RED + default_format + ConsoleColors.RESET
    }

    #def __init__(self, logger_names=None):
    def __init__(self, logger_names=None, fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt=None, style="%"):
        super().__init__()
        # If no logger_names are provided, we'll default to an empty list
        self.logger_names = logger_names or []

    def format(self, record):
        record.shortname = record.name.split('.')[-1]

        # Check if the logger name starts with any of the provided names
        if any(record.name.startswith(logger_name) for logger_name in self.logger_names):
            log_fmt = ConsoleColors.BLUE + self.default_format + ConsoleColors.RESET  # Apply blue formatting
        else:
            log_fmt = LEVEL_COLORS.get(record.levelname, "") + self.default_format + ConsoleColors.RESET

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

    # def format(self, record):
    #     record.shortname = record.name.split('.')[-1]
    #     log_fmt = self.FORMATS.get(record.levelno)
    #     formatter = logging.Formatter(log_fmt)
    #     return formatter.format(record)


class FLFilter(logging.Filter):
    """
    A custom logging filter that allows filtering log messages based on logger names and levels.
    """

    def __init__(self, logger_names=["nvflare.app_common", "nvflare.app_opt"]):
        """
        Initialize the filter with specific logger names and levels.

        :param logger_names: List of logger names to apply the INFO level filter.
        :param info_level: Level for specified logger names.
        :param error_level: Level for other loggers.
        """
        super().__init__()
        self.logger_names = logger_names

    def filter(self, record):
        """
        Filter log records based on the logger name and level.

        :param record: The log record to evaluate.
        :return: True if the record should be logged, False otherwise.
        """
        if any(record.name.startswith(name) for name in self.logger_names):
            return record.levelno >= logging.INFO
        #return record.levelno >= logging.ERROR

class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def __init__(self, fmt_dict: dict = None, fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt=None, style="%"):
        self.fmt_dict = fmt_dict if fmt_dict is not None else {
                "timestamp": "asctime",
                "loggerName": "shortname",
                "level": "levelname",
                "message": "message"
            }
        self.datefmt = "%Y-%m-%d %H:%M:%S.%f"
        super().__init__(fmt, datefmt, style)

    def extract_bracket_fields(self, message: str) -> dict:
        bracket_fields = {}
        match = re.search(r"\[(.*?)\]:", message)
        if match:
            pairs = match.group(1).split(", ")
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split("=", 1)
                    bracket_fields[key] = value
        return bracket_fields

    def formatMessage(self, record) -> dict:
        return {fmt_key: record.__dict__.get(fmt_val, '') for fmt_key, fmt_val in self.fmt_dict.items()}

    def format(self, record) -> str:
        record.shortname = record.name.split('.')[-1]
        record.message = record.getMessage()

        bracket_fields = self.extract_bracket_fields(record.message)

        record.asctime = self.formatTime(record)
        formatted_message_dict = self.formatMessage(record)

        message_dict = {k: v for k, v in formatted_message_dict.items() if k != "message"}

        if bracket_fields:
            message_dict["fl_ctx_fields"] = bracket_fields
            record.message = re.sub(r"\[.*?\]:", "", record.message).strip()

        message_dict[self.fmt_dict.get("message", "message")] = record.message

        return json.dumps(message_dict, default=str)


def replace_filenames(obj, dir_path):
    """
    Function to replace 'filename' keys in JSON objects with updated paths.
    Called for every object in the JSON structure.
    """
    if "filename" in obj and isinstance(obj["filename"], str):
        obj["filename"] = os.path.join(dir_path, obj["filename"])
    return obj

def replace_handler(configure_handler, dir_path):
    log_file = os.path.join(dir_path, configure_handler.args[0])
    print(f"\n\t {log_file=}\n")
    log_handler = RotatingFileHandler(log_file, maxBytes=20 * 1024 * 1024, backupCount=10)
    log_handler.setLevel(configure_handler.level)
    log_handler.setFormatter(configure_handler.formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    root_logger.removeHandler(configure_handler)

def read_log_config(file, dir_path=""):
    """
    Reads a logging configuration file and determines whether to use
    dictConfig (for JSON or HOCON formats) or fileConfig (for INI format).

    Args:
        file (str): Path to the configuration file.

    Returns:
        None
    """
    try:
        # Attempt to parse as JSON
        try:
            with open(file, "r") as f:
                config = json.load(f, object_hook=lambda obj: replace_filenames(obj, dir_path))

            print("Loaded logging configuration using dictConfig (JSON).")
            return config
        except json.JSONDecodeError:
            pass

        # Fallback to INI format with fileConfig
        try:
            logging.config.fileConfig(file, disable_existing_loggers=False)

            print("Loaded logging configuration using fileConfig (INI).")
            return
        except Exception as ini_error:
            print(f"Error loading INI format logging configuration: {ini_error}")
            raise ValueError("Unrecognized logging configuration format.")

    except Exception as e:
        print(f"Failed to load logging configuration: {e}")
        raise


def configure_logging(workspace: Workspace):
    log_config_file_path = workspace.get_log_config_file_path()
    assert os.path.isfile(log_config_file_path), f"missing log config file {log_config_file_path}"
    logging.config.fileConfig(fname=log_config_file_path, disable_existing_loggers=False)


def add_log_file_handler(log_file_name):
    root_logger = logging.getLogger()
    main_handler = root_logger.handlers[0]
    file_handler = RotatingFileHandler(log_file_name, maxBytes=20 * 1024 * 1024, backupCount=10)
    file_handler.setLevel(main_handler.level)
    file_handler.setFormatter(main_handler.formatter)
    root_logger.addHandler(file_handler)


def print_loggers_hierarchy(package_name="nvflare", print_class_loggers=False):
    all_loggers = logging.root.manager.loggerDict

    if print_class_loggers:
        # Print loggers outside of the specified package
        class_loggers = [logger for logger in all_loggers.keys() if not logger.startswith(package_name)]
        class_loggers.sort()
        print(f"class loggers ({len(class_loggers)=}):\n")
        for logger_name in class_loggers:
            print(f"{logger_name}")

    # Filter for package loggers and sort for hierarchical printing
    package_loggers = {name: logger for name, logger in all_loggers.items() if name.startswith(package_name)}
    sorted_loggers = sorted(package_loggers.keys())

    print(f"hierarchical loggers ({len(sorted_loggers)}):")
    def get_effective_level(logger_name):
        """Recursively find the effective level by checking parent loggers."""
        parts = logger_name.split(".")

        # Check each part of the logger name hierarchy from most specific to general
        for i in range(len(parts), 0, -1):
            parent_name = ".".join(parts[:i])
            parent_logger = package_loggers.get(parent_name)
            if isinstance(parent_logger, Logger) and parent_logger.level != logging.NOTSET:
                return logging.getLevelName(parent_logger.level)

        # If no parent has a set level, default to the root logger's effective level
        return logging.getLevelName(logging.root.level)

    def print_hierarchy(logger_name, indent_level=0):
        # Calculate the effective level for the logger name
        logger = package_loggers.get(logger_name)
        level_name = get_effective_level(logger_name)
        # Indicate unset placeholders with "(unset)" if `logger.level == NOTSET`
        is_unset = isinstance(logger, Logger) and logger.level == logging.NOTSET or not isinstance(logger, Logger)
        level_display = f"{level_name} (SET)" if not is_unset else level_name
        # Apply color based on the effective level
        color = LEVEL_COLORS.get(level_name, ConsoleColors.RESET)

        # Print the logger with color and indentation
        print("    " * indent_level + f"{color}{logger_name} [{level_display}]{ConsoleColors.RESET}")

        # Find child loggers based on the current hierarchy level
        for name in sorted_loggers:
            if name.startswith(logger_name + ".") and name.count(".") == logger_name.count(".") + 1:
                print_hierarchy(name, indent_level + 1)

    print_hierarchy(package_name)