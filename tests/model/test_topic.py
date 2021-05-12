"""Topic tests"""

import pytest
import datetime as dt
import sqlalchemy as sqla

from bemserver_core.database import db
from bemserver_core.model import Timeseries
from bemserver_service_acquisition_mqtt.model import (
    Topic, TopicLink, TopicByBroker, TopicBySubscriber)


class TestTopicModel:

    def test_topic_crud(
            self, database, decoder_mosquitto_uptime, broker, subscriber):

        decoder_mosquitto_uptime_cls, decoder = decoder_mosquitto_uptime

        assert Topic.get_by_id(None) is None
        assert Topic.get_by_id(1) is None

        topic = Topic(
            name="$SYS/broker/uptime", payload_decoder_id=decoder.id)
        assert topic.id is None
        topic.save()
        assert topic.id is not None
        assert topic.qos == 1
        assert topic.is_enabled
        assert topic.payload_decoder == decoder
        assert topic.payload_decoder_cls == decoder_mosquitto_uptime_cls
        assert isinstance(
            topic.payload_decoder_instance, decoder_mosquitto_uptime_cls)
        assert topic.links == []
        assert topic.brokers == []
        assert topic.subscribers == []

        assert Topic.get_by_id(topic.id) == topic

        # Add links to topic.
        assert len(decoder.fields) > 0
        for payload_field in decoder.fields:
            ts = Timeseries(name=f"Timeseries {payload_field.name}")
            db.session.add(ts)
            db.session.commit()
            topic_link = topic.add_link(payload_field.id, ts.id)
            assert topic_link.topic == topic
            assert topic_link.payload_field == payload_field
            assert topic_link.timeseries == ts

        assert len(topic.links) == len(decoder.fields)
        assert [x.payload_field.name for x in topic.links] == [
            x.name for x in decoder.fields]

        # Remove links from topic.
        topic.remove_link(666, ts.id)
        assert len(topic.links) == len(decoder.fields)
        topic.remove_link(decoder.fields[0].id, 666)
        assert len(topic.links) == len(decoder.fields)
        topic.remove_link(decoder.fields[0].id, ts.id)
        assert len(topic.links) == len(decoder.fields) - 1
        topic.add_link(decoder.fields[0].id, ts.id)
        assert len(topic.links) == len(decoder.fields)

        # Add relation between topic and broker.
        topic_by_broker = topic.add_broker(broker.id)
        assert topic_by_broker.topic_id == topic.id
        assert topic_by_broker.broker_id == broker.id
        assert topic.brokers == [broker]
        with pytest.raises(sqla.exc.IntegrityError):
            topic.add_broker(666)

        # Remove relation between topic and broker.
        topic.remove_broker(broker.id)
        assert topic.brokers == []
        # No problem if we remove a relation to an inexistant broker.
        topic.remove_broker(666)

        # Add relation between topic and subscriber.
        topic_by_subscriber = topic.add_subscriber(subscriber.id)
        assert topic_by_subscriber.topic_id == topic.id
        assert topic_by_subscriber.subscriber_id == subscriber.id
        assert topic.subscribers == [subscriber]
        with pytest.raises(sqla.exc.IntegrityError):
            topic.add_subscriber(666)

        ts_now = dt.datetime.now(dt.timezone.utc)
        topic.update_subscription(subscriber.id, True)
        assert topic_by_subscriber.is_subscribed
        assert topic_by_subscriber.timestamp_last_subscription is not None
        assert topic_by_subscriber.timestamp_last_subscription > ts_now
        ts_last_sub = topic_by_subscriber.timestamp_last_subscription

        topic.update_subscription(subscriber.id, False)
        assert not topic_by_subscriber.is_subscribed
        assert topic_by_subscriber.timestamp_last_subscription == ts_last_sub

        # Remove relation between topic and subscriber.
        topic.remove_subscriber(subscriber.id)
        assert topic.subscribers == []
        # No problem if we remove a relation to an inexistant subscriber.
        topic.remove_subscriber(666)

        # Save errors.
        topic.qos = 666
        with pytest.raises(ValueError) as exc:
            topic._verify_consistency()
            assert str(exc) == "Invalid QoS level!"

        topic.qos = 2
        topic.payload_decoder_id = 666
        with pytest.raises(sqla.exc.IntegrityError):
            topic.save()

        topic.delete()
        assert Topic.get_by_id(topic.id) is None

        topic.delete()  # try to delete again
        assert Topic.get_by_id(topic.id) is None

        topic.save()
        assert Topic.get_by_id(topic.id) is not None
        assert len(topic.links) == 0

    def test_topic_delete_cascade(
            self, database, mosquitto_topic, broker, subscriber):

        topic_id = mosquitto_topic.id
        assert len(mosquitto_topic.links) > 0
        mosquitto_topic.add_broker(broker.id)
        assert len(mosquitto_topic.brokers) > 0
        mosquitto_topic.add_subscriber(subscriber.id)
        assert len(mosquitto_topic.subscribers) > 0

        mosquitto_topic.delete()
        assert Topic.get_by_id(topic_id) is None

        # Deleting a topic also deletes in cascade links...
        stmt = sqla.select(TopicLink).filter(TopicLink.topic_id == topic_id)
        rows = db.session.execute(stmt).all()
        assert len(rows) == 0

        # ...relations to broker...
        stmt = sqla.select(TopicByBroker)
        stmt = stmt.filter(TopicByBroker.topic_id == topic_id)
        rows = db.session.execute(stmt).all()
        assert len(rows) == 0

        # ...and relations to subscriber.
        stmt = sqla.select(TopicBySubscriber)
        stmt = stmt.filter(TopicBySubscriber.topic_id == topic_id)
        rows = db.session.execute(stmt).all()
        assert len(rows) == 0


class TestTopicLinkModel:

    def test_topic_link_crud(
            self, database, subscriber, mosquitto_topic_name,
            decoder_mosquitto_uptime):

        _, decoder = decoder_mosquitto_uptime

        topic = Topic(
            name=mosquitto_topic_name, payload_decoder_id=decoder.id)
        topic.save()

        assert topic.links == []

        for payload_field in decoder.fields:
            ts = Timeseries(name=f"Timeseries {payload_field.name}")
            db.session.add(ts)
            db.session.commit()
            topic_link = TopicLink(
                topic_id=topic.id, payload_field_id=payload_field.id,
                timeseries_id=ts.id)
            topic_link.save()
            assert topic_link.topic == topic
            assert topic_link.payload_field == payload_field
            assert topic_link.timeseries == ts

        assert len(topic.links) == len(decoder.fields)
        assert [x.payload_field.name for x in topic.links] == [
            x.name for x in decoder.fields]

        # Verify unique constraints between:
        #   - topic and payload field
        #   - topic and timeseries
        topic_link = TopicLink(
            topic_id=topic.id,
            payload_field_id=topic.links[0].payload_field_id,
            timeseries_id=topic.links[0].timeseries_id)
        with pytest.raises(sqla.exc.IntegrityError):
            topic_link.save()

        payload_field_test = decoder.add_field("test")
        topic_link.payload_field_id = payload_field_test.id
        with pytest.raises(sqla.exc.IntegrityError):
            topic_link.save()

        ts_test = Timeseries(name="Timeseries test")
        db.session.add(ts_test)
        db.session.commit()
        topic_link.payload_field_id = topic.links[0].payload_field_id
        topic_link.timeseries_id = ts_test.id
        with pytest.raises(sqla.exc.IntegrityError):
            topic_link.save()

        topic_link.payload_field_id = payload_field_test.id
        topic_link.save()
        assert len(topic.links) == 2

        topic_link.delete()
        assert len(topic.links) == 1


class TestTopicByBrokerModel:

    def test_topic_by_broker(
            self, database, decoder_mosquitto_uptime, broker):

        _, decoder = decoder_mosquitto_uptime

        assert len(broker.topics) == 0

        topic = Topic(name="test", payload_decoder_id=decoder.id)
        topic.save()
        assert len(topic.brokers) == 0

        topic.add_broker(broker.id)
        assert topic.brokers == [broker]
        assert broker.topics == [topic]

        topic_by_broker = TopicByBroker.get_by_id((topic.id, broker.id,))
        assert topic_by_broker.is_enabled

        topic.remove_broker(broker.id)
        assert len(topic.brokers) == 0
        assert len(broker.topics) == 0

        topic_by_broker = TopicByBroker.get_by_id((topic.id, broker.id,))
        assert topic_by_broker is None


class TestTopicBySubscriberModel:

    def test_topic_by_subscriber(
            self, database, decoder_mosquitto_uptime, subscriber):

        _, decoder = decoder_mosquitto_uptime

        assert len(subscriber.topics) == 0

        topic = Topic(name="test", payload_decoder_id=decoder.id)
        topic.save()
        assert len(topic.subscribers) == 0

        topic.add_subscriber(subscriber.id)
        assert len(topic.subscribers) == 1
        assert len(subscriber.topics) == 1

        topic_by_subscriber = TopicBySubscriber.get_by_id(
            (topic.id, subscriber.id,))
        assert topic_by_subscriber.is_enabled
        assert not topic_by_subscriber.is_subscribed
        assert topic_by_subscriber.timestamp_last_subscription is None

        ts_now = dt.datetime.now(dt.timezone.utc)
        topic.update_subscription(subscriber.id, True)
        assert topic_by_subscriber.is_subscribed
        assert topic_by_subscriber.timestamp_last_subscription is not None
        assert topic_by_subscriber.timestamp_last_subscription > ts_now
        ts_last_sub = topic_by_subscriber.timestamp_last_subscription

        topic_by_subscriber.update_subscription(False)
        assert not topic_by_subscriber.is_subscribed
        assert topic_by_subscriber.timestamp_last_subscription == ts_last_sub

        topic.remove_subscriber(subscriber.id)
        assert len(topic.subscribers) == 0
        assert len(subscriber.topics) == 0
