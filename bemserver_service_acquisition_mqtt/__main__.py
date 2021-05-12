#!/usr/bin/env python3
"""Launch MQTT acquisition service."""

import os
import sys
import argparse
import json
import time
import re
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import bemserver_service_acquisition_mqtt as svc
from bemserver_service_acquisition_mqtt.service import Service
from bemserver_service_acquisition_mqtt.exceptions import ServiceError


logger = logging.getLogger(svc.SERVICE_LOGNAME)


def main():
    """Main program."""
    cmd_args = parse_command_line(sys.argv)
    svc_config = load_config(cmd_args.config_filepath)
    init_logger(svc_config["logging"], verbose=cmd_args.verbose)
    launch_service(svc_config)
    return True


def _argtype_readable_file(str_value):
    """Check that a path value exists as a valid readable file.

    :param str str_value: Input string argument value.
    :returns Path: A readable file absolute path.
    :raises argparse.ArgumentTypeError:
        When the path value is either not a valid file or not readable.
    """
    file_path = Path(str_value)
    if not file_path.is_file():
        raise argparse.ArgumentTypeError(
            f"Invalid readable_file value, not a file: {file_path}")
    absolute_file_path = file_path.resolve()
    if not os.access(str(absolute_file_path), os.R_OK):
        raise argparse.ArgumentTypeError(
            f"Invalid readable_file value, not readable: {file_path}")
    return absolute_file_path


def parse_command_line(argv):
    """Parse command line argument. See -h option

    :param list argv: Arguments on command line must include caller file name.
    :returns argparse.Namespace: Argument values.
    """
    formatter_class = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(
        description=svc.__description__, formatter_class=formatter_class)

    parser.add_argument(
        "--version", action="version", version=(
            f"{svc.__binname__}\tversion {svc.__version__}"
            f"\n{svc.__description__}\n(c) 2021 {svc.__author__}"),
    )
    parser.add_argument(
        dest="config_filepath", type=_argtype_readable_file,
        help="configuration file path to use",
    )
    parser.add_argument(
        "-v", "--verbose", dest="verbose", action="store_true", default=False,
        help="print log messages",
    )

    # Parse and return command line arguments.
    return parser.parse_args(argv[1:])


def load_config(config_filepath, *, verify=True):
    """Load service configuration from JSON file.

    :param Path config_filepath: Service config file path.
    :returns dict: Service parameters.
    """
    svc_config = {}
    with config_filepath.open("r") as config_file:
        svc_config = json.load(config_file)
    # If wanted, check configuration content.
    if verify:
        assert "db_url" in svc_config
        assert "working_dirpath" in svc_config
        assert "logging" in svc_config
    return svc_config


def init_logger(log_config, *, verbose=False):
    """Initialize service logger.

    :param dict log_config: An instance of service log configuration.
    :param bool verbose: (optional, default False)
        Print log messages in console output.
    """
    # Create our custom record formatters.
    defaultFormat = (
        "%(asctime)s %(levelname)-8s"
        " [%(name)s].[%(filename)s:%(funcName)s:%(lineno)d]"
        " [%(processName)s:%(process)d].[%(threadName)s:%(thread)d]"
        " || %(message)s")
    formatter = logging.Formatter(log_config.get("format", defaultFormat))
    formatter.converter = time.gmtime

    # Configure logger.
    logger.setLevel(log_config.get("level", logging.WARNING))
    # Create a stream handler (console out) for logger.
    if verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.NOTSET)  # inherits logger's level
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    # Create a daily rotated log file handler for logger.
    # See example: http://stackoverflow.com/a/25387192
    if "dirpath" in log_config:
        logfile_handler = TimedRotatingFileHandler(
            Path(log_config["dirpath"]) / f"{svc.__binname__}.log",
            when="midnight", backupCount=log_config["history"], utc=True)
        logfile_handler.suffix = "%Y-%m-%d"
        logfile_handler.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        logfile_handler.setLevel(logging.NOTSET)  # inherits logger's level
        logfile_handler.setFormatter(formatter)
        logger.addHandler(logfile_handler)

    # Do not propagate logging to handlers if disabled.
    logger.propagate = log_config.get("enabled", True)

    logger.info("Logger initialized, [%s] level.",
                logging.getLevelName(logger.level))
    if "dirpath" in log_config:
        logger.info("Current log folder path ([%d] days backup): [%s]",
                    log_config["history"], str(log_config["dirpath"]))


def launch_service(svc_config):
    """Launch MQTT acquisition service .

    Relies on brokers, subscribers and topics stored in database.
    """
    logger.info("Launching MQTT acquisition service (PID %s)...", os.getpid())
    service = Service(svc_config["working_dirpath"])
    service.set_db_url(svc_config["db_url"])
    try:
        service.run()
    except ServiceError as exc:
        logger.error("MQTT acquisition service error: %s", str(exc))


if __name__ == "__main__":

    sys.exit(main())
