import logging
import sys
import os
import re
from ast import literal_eval
import importlib.util
from pathlib import Path

from typing import Union, List, Dict, Any, Union


def import_if_installed(library_name):
    lib = None
    if importlib.util.find_spec(library_name) is not None:
        lib = importlib.import_module(library_name)
        logging.debug(f"{library_name} is installed and has been imported.")
    else:
        logging.debug(f"{library_name} is not installed.")
    return lib


def camel_case_split(identifier):
    matches = re.finditer(".+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)", identifier)
    return [m.group(0) for m in matches]


def get_env_variable(key: Union[str, List[str]], default_value, check_for_prefix: bool = False) -> Any:

    prefix = ""
    if check_for_prefix and ("PREFIX" in os.environ):
        prefix = f"{os.environ['PREFIX']}_"

    if isinstance(key, str):
        key = [key]

    for ky in key:
        # name of the environment variable to look for
        nm = f"{prefix}{ky}"
        if nm in os.environ:
            return cast(os.environ[nm])
    return default_value


def get_environment_variables(prefix: str = None, with_prefix: bool = True) -> Dict[str, Any]:
    re_prefix = re.compile(prefix if prefix is not None else "")
    config = dict()
    for ky in os.environ:
        m = re_prefix.match(ky)
        if m:
            nm = ky if with_prefix else ky[m.end():]
            config[nm] = cast(os.environ[ky])
    return config


def default_from_env(key: Union[str, List[str]], default: Any) -> Any:
    return get_env_variable(key, default, check_for_prefix=True)


re_number = re.compile("^[0-9.,]+$")
re_integer = re.compile(r"^\d+$")
re_float = re.compile(r"^((\d+\.(\d+)?)|(\.\d+))$")
re_float_de = re.compile(r"^((\d+,(\d+)?)|(,\d+))$")
re_boolean = re.compile(r"^(true|false)$", re.IGNORECASE | re.ASCII)
re_list_or_tuple_or_dict = re.compile(r"^\s*(\[.*\]|\(.*\)|\{.*\})\s*$", re.ASCII)
re_comma = re.compile(r"^(\".*\")|(\'.*\')$", re.ASCII)


def cast(var: str) -> Union[None, int, float, str, bool]:
    """casting strings to primitive datatypes"""
    if re_number.match(var):
        if re_integer.match(var):  # integer
            var = int(var)
        elif re_float.match(var):  # float
            var = float(var)
        elif re_float_de.match(var):  # float
            var = float(var.replace(",", "."))
    elif re_boolean.match(var):
        var = True if var[0].lower() == "t" else False
    elif re_list_or_tuple_or_dict.match(var):
        var = literal_eval(var)
    elif re_comma.match(var):
        # strip enclosing high comma
        var = var.strip('"').strip('"')
    return var
    
    
def set_env_variable(key: str, val) -> bool:
    os.environ[key] = str(val)
    return True


def cast_logging_level(var: str, default: int = logging.INFO) -> int:
    """Only casts logging levels"""
    # cast string if possible
    if isinstance(var, str):
        var = cast(var)

    options = {
        "debug": logging.DEBUG,  # 10
        "info": logging.INFO,  # 20
        "warning": logging.WARNING,  # 30
        "warn": logging.WARN,  # 30
        "error": logging.ERROR,  # 40
        "critical": logging.CRITICAL,  # 50
        "fatal": logging.FATAL,  # 50
        "notset": logging.NOTSET  # 0
    }
    if isinstance(var, int):
        if var not in options.values():
            return default

    elif isinstance(var, str):
        for ky, val in options.items():
            if var.lower() == ky:
                return val
    else:
        return default
    return var


def get_logging_level(key: str = "LOGGING_LEVEL", default: int = logging.INFO) -> int:
    return cast_logging_level(get_env_variable(key, default))


def setup_logging(
        name: str,
        level: int = logging.INFO,
        use_env_log_level: bool = True,
        period_sec: int = 1
) -> logging.Logger:

    log_file = get_env_variable("LOGFILE", None)
    log_level = get_logging_level("LOGGING_LEVEL", level) if use_env_log_level else level

    # Setup logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)] + # Ensures logs are forwarded to Docker
                 [logging.FileHandler(Path(log_file).with_suffix(".log"))] if log_file is not None else [],

    )
    # create file wide logger
    logger_ = logging.getLogger(name)
    # Add our filter
    if import_if_installed("redis"):
        # package log-rate-limit requires redis to be available
        log_rate_limit = import_if_installed("log_rate_limit")
        if log_rate_limit:
            logger_.addFilter(log_rate_limit.StreamRateLimitFilter(period_sec=period_sec))

    # first log message
    logger_.info(f"Logging configured: level={log_level}, file={log_file}")

    return logger_


# Setup logging
logger = setup_logging(__name__)

