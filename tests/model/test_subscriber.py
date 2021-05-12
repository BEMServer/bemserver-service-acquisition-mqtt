"""Subscriber tests"""

import time
import json
import logging
import pytest
import datetime as dt
import sqlalchemy as sqla
from pathlib import Path

from bemserver_core.database import db
from bemserver_core.model import TimeseriesData
from bemserver_service_acquisition_mqtt.model import (
    Subscriber, Topic, TopicBySubscriber)


class TestSubscriberModel:

    def test_subscriber_crud(self, database, broker):

        assert Subscriber.get_by_id(None) is None
        assert Subscriber.get_by_id(1) is None

        subscriber = Subscriber(broker_id=broker.id)
        assert subscriber.id is None
        subscriber.save()
        assert subscriber.id is not None
        assert subscriber.is_enabled
        assert subscriber.keep_alive == 60
        assert subscriber.use_persistent_session
        assert subscriber.session_expiry == 3600
        assert subscriber.broker == broker
        assert subscriber.username is None
        assert subscriber.password is None
        assert not subscriber.must_authenticate

        assert Subscriber.get_by_id(subscriber.id) == subscriber

        # Missing subscriber username for authentication.
        broker.is_auth_required = True
        with pytest.raises(ValueError) as exc:
            subscriber._verify_consistency()
            assert str(exc) == "Broker requires username authentication!"
        broker.is_auth_required = False

        assert subscriber.topics == []

        subscriber.delete()
        assert Subscriber.get_by_id(subscriber.id) is None

        subscriber.delete()  # try to delete again
        assert Subscriber.get_by_id(subscriber.id) is None

        subscriber.save()
        assert Subscriber.get_by_id(subscriber.id) is not None

    def test_subscriber_topics(self, database, subscriber, topic):

        assert subscriber.topics == []
        assert topic.subscribers == []
        topic.add_subscriber(subscriber.id)
        assert subscriber.topics == [topic]
        assert topic.subscribers == [subscriber]

        # Deleting subscriber do not affect topics.
        subscriber.delete()
        assert Subscriber.get_by_id(subscriber.id) is None
        assert Topic.get_by_id(topic.id) == topic

    def test_subscriber_get_list(self, database, broker):

        rows = Subscriber.get_list()
        assert len(rows) == 0

        subscriber = Subscriber(broker_id=broker.id)
        subscriber.save()
        subscriber2 = Subscriber(
            broker_id=broker.id, use_persistent_session=False)
        subscriber2.save()

        rows = Subscriber.get_list()
        assert len(rows) == 2
        assert rows[0][0].id == subscriber.id
        assert rows[1][0].id == subscriber2.id

        subscriber2.is_enabled = False
        subscriber2.save()

        rows = Subscriber.get_list(is_enabled=True)
        assert len(rows) == 1
        assert rows[0][0].id == subscriber.id

        rows = Subscriber.get_list(is_enabled=False)
        assert len(rows) == 1
        assert rows[0][0].id == subscriber2.id

    def test_subscriber_connect(self, database, subscriber, client_id):

        assert subscriber._client_id is None
        assert subscriber._client is None
        assert not subscriber.is_connected
        assert subscriber.timestamp_last_connection is None
        subscriber.connect(client_id)
        assert subscriber._client_id == client_id
        assert subscriber._client is not None
        assert subscriber._client.is_connected()
        assert subscriber.is_connected
        ts_connection = subscriber.timestamp_last_connection
        assert subscriber.timestamp_last_connection is not None

        subscriber.disconnect()
        assert not subscriber._client.is_connected()
        assert not subscriber.is_connected
        assert subscriber.timestamp_last_connection == ts_connection

        # Verify persistent session feature.
        assert subscriber.use_persistent_session
        subscriber.connect(client_id)
        assert subscriber._client.is_connected()
        assert subscriber._client_session_present
        assert subscriber.is_connected
        assert subscriber.timestamp_last_connection > ts_connection
        ts_connection = subscriber.timestamp_last_connection
        subscriber.disconnect()
        assert not subscriber._client.is_connected()
        assert not subscriber.is_connected
        subscriber.connect()  # reconnect without client_id
        assert subscriber._client.is_connected()
        assert not subscriber._client_session_present
        subscriber.disconnect()
        assert not subscriber._client.is_connected()
        assert not subscriber.is_connected

        # Disable persistent session feature.
        subscriber.use_persistent_session = False
        subscriber.connect(client_id)  # here client_id is optional and useless
        assert subscriber._client.is_connected()
        subscriber.disconnect()
        assert not subscriber._client.is_connected()
        assert not subscriber.is_connected
        subscriber.connect(client_id)
        assert subscriber._client.is_connected()
        assert not subscriber._client_session_present
        subscriber.disconnect()
        assert not subscriber._client.is_connected()
        assert not subscriber.is_connected

    def test_subscriber_on_message(
            self, database, subscriber, client_id, topic, publisher):

        assert topic.is_enabled
        topic.add_subscriber(subscriber.id)

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

        # Get subscription state for the couple topic/subscriber.
        topic_by_subscriber = TopicBySubscriber.get_by_id(
            (topic.id, subscriber.id,))
        assert not topic_by_subscriber.is_subscribed

        # Do not use a persistent session.
        subscriber.use_persistent_session = False
        subscriber.connect()  # non persistent session: client ID not needed
        assert subscriber.is_connected
        assert topic_by_subscriber.is_subscribed

        # Wait just enough time to get retained message, at least.
        time.sleep(0.5)

        # Verify that messages have been processed and saved to database.
        rows = db.session.execute(stmt).all()
        assert len(rows) == 1  # only retained message has been stored
        assert rows[0][0].value == 42

        subscriber.disconnect()
        assert not subscriber.is_connected
        assert not topic_by_subscriber.is_subscribed

        # As session was not persistent, subscriptions are lost on broker-side
        #  and messages are not stored for the subscriber.
        # Let's publish 2 messages to verify this.
        for i in range(2):
            payload = {
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                "value": 50 + i,
            }
            msg_info = publisher.publish(
                topic=topic.name, payload=json.dumps(payload), qos=1,
                retain=True)
            msg_info.wait_for_publish()

        # Reconnect and resubscribe.
        subscriber.connect()
        assert subscriber.is_connected
        assert topic_by_subscriber.is_subscribed

        # Wait just enough time to get the new retained message.
        time.sleep(0.5)

        # Verify that 1 message is lost and just the last has been processed.
        rows = db.session.execute(stmt).all()
        assert len(rows) == 2
        assert rows[1][0].value == 51

        # And disconnect.
        subscriber.disconnect()
        assert not subscriber.is_connected

        # Now use a persistent session.
        subscriber.use_persistent_session = True
        subscriber.connect(client_id)
        assert subscriber.is_connected
        # After first connection, persistent session is not present yet.
        assert not subscriber._client_session_present
        assert topic_by_subscriber.is_subscribed

        # Wait just enough time to get retained message, at least.
        time.sleep(0.5)

        for i in range(4):
            payload = {
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                "value": 666 + i,
            }
            msg_info = publisher.publish(
                topic=topic.name, payload=json.dumps(payload), qos=1,
                retain=True)
            msg_info.wait_for_publish()
            # Disconnect subscriber after the first message.
            if i == 1:
                subscriber.disconnect()
                assert not subscriber.is_connected
                assert not topic_by_subscriber.is_subscribed

        # Reconnect subscriber with client ID to its persistent session.
        subscriber.connect(client_id)
        assert subscriber.is_connected
        # At second connection, persistent session is present.
        assert subscriber._client_session_present
        assert topic_by_subscriber.is_subscribed

        # Wait just enough time to get all messages.
        time.sleep(1)

        # Verify that new message has been processed.
        rows = db.session.execute(stmt).all()
        assert len(rows) == 6
        assert rows[2][0].value == 666
        assert rows[3][0].value == 667
        assert rows[4][0].value == 668
        assert rows[5][0].value == 669

        # And disconnect.
        subscriber.disconnect()
        assert not subscriber.is_connected
        assert not topic_by_subscriber.is_subscribed

    def test_subscriber_unsubscribe(
            self, database, subscriber, client_id, topic, publisher):

        assert topic.is_enabled
        topic.add_subscriber(subscriber.id)

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

        # Get subscription state for the couple topic/subscriber.
        topic_by_subscriber = TopicBySubscriber.get_by_id(
            (topic.id, subscriber.id,))
        assert not topic_by_subscriber.is_subscribed

        subscriber.connect(client_id)
        assert subscriber.is_connected
        assert topic_by_subscriber.is_subscribed

        # Wait just enough time to get retained message, at least.
        time.sleep(0.5)

        # Verify that messages have been processed and saved to database.
        rows = db.session.execute(stmt).all()
        assert len(rows) == 1
        assert rows[0][0].value == 42

        # Unsubscribe from topic.
        subscriber.unsubscribe_all()
        assert not topic_by_subscriber.is_subscribed
        time.sleep(0.2)
        # Publish a new message, the subscriber should not receive it.
        payload = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "value": 666,
        }
        msg_info = publisher.publish(
            topic=topic.name, payload=json.dumps(payload), qos=1, retain=True)
        msg_info.wait_for_publish()

        # Verify that no new message has been processed and saved to database.
        rows = db.session.execute(stmt).all()
        assert len(rows) == 1
        assert rows[0][0].value == 42

        subscriber.disconnect()
        assert not subscriber.is_connected

    def test_subscriber_logger(
            self, database, subscriber, topic, publisher, tmpdir):

        topic.add_subscriber(subscriber.id)

        logger = logging.getLogger("mqtt_subscriber_logger")
        logger.setLevel(logging.DEBUG)
        log_filepath = Path(str(tmpdir)) / "acquisition_mqtt.log"
        logfile_handler = logging.FileHandler(log_filepath)
        logfile_handler.setLevel(logging.NOTSET)
        logger.addHandler(logfile_handler)

        # Log file exists and is empty.
        assert log_filepath.exists()
        with log_filepath.open("r") as logfile:
            assert len(logfile.read()) <= 0

        # Connect/disconnect without logger.
        subscriber.connect()
        subscriber.disconnect()

        # Log file is still empty.
        with log_filepath.open("r") as logfile:
            assert len(logfile.read()) <= 0

        subscriber.connect(logger=logger)
        time.sleep(0.5)
        subscriber.disconnect()

        # Timeseries data has been received.
        stmt = sqla.select(TimeseriesData)
        for topic_link in topic.links:
            stmt = stmt.filter(
                TimeseriesData.timeseries_id == topic_link.timeseries_id
            )
        stmt = stmt.order_by(
            TimeseriesData.timestamp
        )
        rows = db.session.execute(stmt).all()
        assert len(rows) == 1
        assert rows[0][0].value == 42

        # And log file exists and is not empty.
        assert log_filepath.exists()
        with log_filepath.open("r") as logfile:
            assert len(logfile.read()) > 0
