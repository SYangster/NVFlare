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
import logging
import os
import json
import re
from logging import Logger
from logging.handlers import RotatingFileHandler

from nvflare.apis.workspace import Workspace


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
    """
    Formatter to shorten logger names to the suffix"
    """
    def __init__(self, fmt=None, datefmt=None, style="%"):
        # Default fmt if not provided, replace %(name)s with %(shortname)s
        fmt = fmt or "%(asctime)s - %(shortname)s - %(levelname)s - %(message)s"
        fmt = fmt.replace("%(name)s", "%(shortname)s")
        self.fmt = fmt
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def format(self, record):
        # set shortname to name of Logger after last "."
        record.shortname = record.name.split('.')[-1]
        return super().format(record)

class ColorFormatter(ShortNameFormatter):
    """
    Formatter that applies colors based on log levels. Optionally can color logger_names.
    """
    def __init__(self, fmt=None, datefmt=None, style="%", logger_names=None):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.logger_names = logger_names or []

    def format(self, record):
        super().format(record)

        # Check if the logger name starts with any of the provided names
        if record.levelno <= logging.INFO and any(record.name.startswith(logger_name) for logger_name in self.logger_names):
            log_fmt = ConsoleColors.BLUE + self.fmt  + ConsoleColors.RESET 
        else:
            log_fmt = LEVEL_COLORS.get(record.levelname, "") + self.fmt  + ConsoleColors.RESET

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class FLFilter(logging.Filter):
    """
    Filter that allows filtering log messages based on logger names.
    """

    def __init__(self, logger_names=["nvflare.app_common", "nvflare.app_opt"]):
        super().__init__()
        self.logger_names = logger_names

    def filter(self, record):
        #Filter log records based on the logger name
        if any(record.name.startswith(name) for name in self.logger_names):
            return record.levelno >= logging.INFO
        #return record.levelno >= logging.ERROR

class JsonFormatter(ShortNameFormatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def __init__(self, fmt=None, datefmt=None, style="%", fmt_dict: dict = None):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.fmt_dict = fmt_dict or {
                "timestamp": "asctime",
                "loggerName": "shortname",
                "level": "levelname",
                "message": "message"
            }

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
        super().format(record)
        #record.shortname = record.name.split('.')[-1]
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
    """Function to replace 'filename' keys in JSON objects with updated paths."""
    if "filename" in obj and isinstance(obj["filename"], str):
        obj["filename"] = os.path.join(dir_path, obj["filename"])
    return obj


def read_log_config(file, dir_path=""):
    """
    Reads a logging configuration file and determines whether to use
    dictConfig (JSON format) or fileConfig (INI format).

    Args:
        file (str): Path to the configuration file.

    Returns:
        config (dict) if JSON else None
    """
    json_error = None
    ini_error = None

    # dictConfig JSON format
    try:
        with open(file, "r") as f:
            config = json.load(f, object_hook=lambda obj: replace_filenames(obj, dir_path))
        return config
    except Exception as e:
        json_error = e

    # fileConfig INI format
    try:
        logging.config.fileConfig(file, disable_existing_loggers=False)
        return
    except Exception as e:
        ini_error = e
    
    if json_error or ini_error:
        raise ValueError(f"Unrecognized logging configuration format. Failed to parse JSON: {json_error}. Failed to parse INI: {ini_error}.")


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


def print_loggers_hierarchy(package_name="nvflare", print_external_loggers=False):
    all_loggers = logging.root.manager.loggerDict

    # Print loggers outside of the specified package
    if print_external_loggers:
        external_loggers = [logger for logger in all_loggers.keys() if not logger.startswith(package_name)]
        external_loggers.sort()
        print(f"external loggers ({len(external_loggers)=}):\n")
        for logger_name in external_loggers:
            print(f"{logger_name}")

    # Filter for package loggers and sort for hierarchical printing
    package_loggers = {name: logger for name, logger in all_loggers.items() if name.startswith(package_name)}
    sorted_loggers = sorted(package_loggers.keys())
    print(f"hierarchical loggers ({len(sorted_loggers)}):")

    def get_effective_level(logger_name):
        # Recursively find the effective level by checking parent loggers
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