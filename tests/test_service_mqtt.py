"""Service tests"""

import time
import argparse
import json
import logging
import pytest
import sqlalchemy as sqla
from pathlib import Path

from bemserver_core.database import db
from bemserver_core.model import TimeseriesData
from bemserver_service_acquisition_mqtt.model import TopicBySubscriber
from bemserver_service_acquisition_mqtt.service import Service
from bemserver_service_acquisition_mqtt import SERVICE_LOGNAME
from bemserver_service_acquisition_mqtt.__main__ import (
    _argtype_readable_file, load_config, init_logger)
from bemserver_service_acquisition_mqtt.exceptions import ServiceError


class TestServiceMQTT:

    def test_service_mqtt_set_db_url(self, db_url, tmpdir):

        svc = Service(str(tmpdir))
        assert db.engine is None
        svc.set_db_url(db_url)
        assert db.engine is not None
        assert str(db.engine.url) == db_url

    def test_service_mqtt_set_db_url_already_done(
            self, db_url, tmpdir, database):

        svc = Service(str(tmpdir))
        assert db.engine is not None
        assert str(db.engine.url) == db_url
        svc.set_db_url(db_url)
        assert db.engine is not None
        assert str(db.engine.url) == db_url

    def test_service_mqtt_run(
            self, tmpdir, database, subscriber, topic, publisher):

        assert topic.is_enabled

        assert subscriber.is_enabled
        assert not subscriber.is_connected

        topic_by_subscriber = topic.add_subscriber(subscriber.id)
        assert not topic_by_subscriber.is_subscribed

        # No timeseries data yet.
        stmt = sqla.select(TimeseriesData)
        for topic_link in topic.links:
            stmt = stmt.filter(
                TimeseriesData.timeseries_id == topic_link.timeseries_id
            )
        stmt = stmt.order_by(
            TimeseriesData.timestamp
        )
        rows = db.session.execute(stmt).all()
        assert len(rows) == 0

        svc = Service(str(tmpdir))
        assert not svc.is_running
        assert svc._running_subscribers == []
        svc.run()
        assert svc.is_running
        assert subscriber.is_connected
        assert topic_by_subscriber.is_subscribed
        assert len(svc._running_subscribers) == 1
        assert subscriber.id in [x.id for x in svc._running_subscribers]

        # Waiting for messages.
        time.sleep(1)

        svc.stop()
        assert not svc.is_running
        assert not subscriber.is_connected
        assert not topic_by_subscriber.is_subscribed
        assert svc._running_subscribers == []

        # At least one timeseries data received.
        rows = db.session.execute(stmt).all()
        assert len(rows) >= 1

    def test_service_mqtt_run_tls(
            self, tmpdir, database, subscriber_tls, topic, publisher):

        assert topic.is_enabled

        assert subscriber_tls.is_enabled
        assert not subscriber_tls.is_connected

        topic_by_subscriber = topic.add_subscriber(subscriber_tls.id)
        assert not topic_by_subscriber.is_subscribed

        # No timeseries data yet.
        stmt = sqla.select(TimeseriesData)
        for topic_link in topic.links:
            stmt = stmt.filter(
                TimeseriesData.timeseries_id == topic_link.timeseries_id
            )
        stmt = stmt.order_by(
            TimeseriesData.timestamp
        )
        rows = db.session.execute(stmt).all()
        assert len(rows) == 0

        svc = Service(str(tmpdir))
        assert not svc.is_running
        assert svc._running_subscribers == []
        svc.run()
        assert svc.is_running
        assert subscriber_tls.is_connected
        assert topic_by_subscriber.is_subscribed
        assert len(svc._running_subscribers) == 1
        assert subscriber_tls.id in [x.id for x in svc._running_subscribers]

        # Waiting for messages.
        time.sleep(1)

        svc.stop()
        assert not svc.is_running
        assert not subscriber_tls.is_connected
        assert not topic_by_subscriber.is_subscribed
        assert svc._running_subscribers == []

        # At least one timeseries data received.
        rows = db.session.execute(stmt).all()
        assert len(rows) >= 1

    def test_service_mqtt_nothing_to_do(self, db_url, tmpdir):
        svc = Service(str(tmpdir))
        svc.set_db_url(db_url)
        db.setup_tables()  # init database (for this test only)
        with pytest.raises(ServiceError) as exc:
            svc.run()
            assert str(exc) == (
                "No subscribers available to run MQTT acquisition!")
        assert svc._running_subscribers == []

    def test_service_mqtt_main_argtype_readable_file(self, tmpdir):
        filepath = Path(str(tmpdir)) / "test.txt"

        # File does not exist.
        with pytest.raises(argparse.ArgumentTypeError):
            _argtype_readable_file(filepath)

        # Create file to pass argtype validator.
        filepath.touch()
        assert _argtype_readable_file(filepath) == filepath

        # Deny file reading to owner.
        file_stat = filepath.stat()
        file_stat_mode_backup = file_stat.st_mode
        filepath.chmod(0o144)
        # File read access is not allowed.
        with pytest.raises(argparse.ArgumentTypeError):
            _argtype_readable_file(filepath)
        filepath.chmod(file_stat_mode_backup)

    def test_service_mqtt_main_load_config(self, json_service_config, tmpdir):
        filepath = Path(str(tmpdir)) / "service-config.json"

        def write_config_file(service_config):
            with filepath.open("w") as fp:
                json.dump(service_config, fp)

        write_config_file(json_service_config)
        svc_config = load_config(filepath)
        assert svc_config == json_service_config

        del json_service_config["db_url"]
        write_config_file(json_service_config)
        with pytest.raises(AssertionError):
            load_config(filepath)
        load_config(filepath, verify=False)

    def test_service_mqtt_main_init_logger(self, json_service_config):
        log_config = json_service_config["logging"]

        logger = logging.getLogger(SERVICE_LOGNAME)
        assert logger.level != logging.DEBUG
        assert logger.handlers == []

        init_logger(log_config)

        assert logger.level == logging.DEBUG
        assert logger.propagate
        assert len(logger.handlers) == 1
        assert isinstance(
            logger.handlers[0], logging.handlers.TimedRotatingFileHandler)
        assert logger.handlers[0].formatter._fmt == log_config["format"]
        assert logger.handlers[0].level == logging.NOTSET
        assert logger.handlers[0].when.lower() == "midnight"
        assert logger.handlers[0].utc

        logger.removeHandler(logger.handlers[0])
        init_logger(log_config, verbose=True)
        assert len(logger.handlers) == 2
        assert any(
            [isinstance(x, logging.StreamHandler) for x in logger.handlers])

        log_config["enabled"] = False
        init_logger(log_config)
        assert not logger.propagate

        while len(logger.handlers) > 0:
            logger.removeHandler(logger.handlers[0])
