#!/usr/bin/env python3
"""Launch MQTT acquisition service.

This service can be managed through systemd (the service manager for Linux).
See README for deployment instructions.
"""

import os
import sys
import signal
import click
import json
import time
import re
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import bemserver_service_acquisition_mqtt as svc
from bemserver_service_acquisition_mqtt.service import Service
from bemserver_service_acquisition_mqtt.exceptions import ServiceError


service = None
logger = logging.getLogger(svc.SERVICE_LOGNAME)


def signal_term_handler(sigcode, frame):
    """Callback for SIGTERM signal.

    This signal is sent by systemd when the service is stopping.
    """
    sig = signal.Signals(sigcode)
    logger.debug(f"Service received {sig.name} ({sigcode}) signal.")
    stop_service()


signal.signal(signal.SIGTERM, signal_term_handler)


def echo_version(ctx, param, value):
    """Print service version."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(svc.__description__)
    click.echo(f"Version {svc.__version__}")
    click.echo(svc.__copyright__)
    ctx.exit()


@click.command(short_help="Start the service.")
@click.argument(
    "config_file", type=click.types.Path(
        exists=True, resolve_path=True, path_type=Path))
@click.option(
    "-v", "--verbose", is_flag=True, default=False, help="Print log messages.")
@click.option(
    "-d", "--debug", is_flag=True, default=False, help="Set debug mode.")
@click.option(
    "--version", is_flag=True, callback=echo_version, expose_value=False,
    is_eager=True, help="Show application version.")
def main(config_file, verbose, debug):
    """BEMServer service - Timeseries acquisition through MQTT

    CONFIG_FILE is the path name of the service configuration file.
    \f

    :param Path config_file: Service configuration file path.
    :param bool verbose: (optional, default False)
        If True prints log messages in console output.
    :param bool debug: (optional, default False)
        If True forces log level to DEBUG.
    """
    svc_config = load_config(config_file)
    init_logger(svc_config["logging"], verbose=verbose, debug=debug)

    logger.info(f"Service PID: {os.getpid()}...")

    global service
    service = Service(svc_config["working_dirpath"])
    service.set_db_url(svc_config["db_url"])
    try:
        service.run()
    except ServiceError as exc:
        logger.error(f"MQTT acquisition service error: {str(exc)}")

    try:
        while service.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.warning("Service received Ctrl+C and will stop.")
    finally:
        stop_service()


def stop_service():
    """Stop the service and exit program."""
    if service is None:
        logger.warning("Can not stop service as it is not even instantiated!")
        sys.exit(666)

    if not service.is_running:
        logger.warning("Can not stop service as it is not running!")
        sys.exit(666)

    service.stop()
    sys.exit(0)


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


def init_logger(log_config, *, verbose=False, debug=False):
    """Initialize service logger.

    :param dict log_config: An instance of service log configuration.
    :param bool verbose: (optional, default False)
        If True prints log messages in console output.
    :param bool debug: (optional, default False)
        If True forces log level to DEBUG.
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
    logger.setLevel(
        logging.DEBUG if debug else log_config.get("level", logging.WARNING))
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

    logger.info(
        f"Logger initialized, [{logging.getLevelName(logger.level)}] level.")
    if "dirpath" in log_config:
        logger.info(
            f"Current log folder path ([{log_config['history']}] days backup):"
            f" [{str(log_config['dirpath'])}]")


if __name__ == "__main__":

    main()
