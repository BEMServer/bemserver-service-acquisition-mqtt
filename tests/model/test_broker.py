"""Broker tests"""

import ssl
import pytest
import sqlalchemy as sqla
import paho.mqtt.client as mqttc

from bemserver_service_acquisition_mqtt.model import Broker, Subscriber


class TestBrokerModel:

    def test_broker_crud(self, database, mosquitto_topic):

        assert Broker.get_by_id(None) is None
        assert Broker.get_by_id(1) is None

        broker = Broker(host="test.mosquitto.org", port=1883)
        assert broker.id is None
        broker.save()
        assert broker.id is not None
        assert broker.protocol_version == mqttc.MQTTv5
        assert broker.transport == "tcp"
        assert not broker.is_auth_required
        assert not broker.use_tls
        assert broker.tls_version == ssl.PROTOCOL_TLSv1_2
        assert broker.tls_verifymode == ssl.CERT_OPTIONAL
        assert broker.tls_certificate is None

        assert Broker.get_by_id(broker.id) == broker

        assert broker.subscribers == []
        subscriber = Subscriber(broker_id=broker.id)
        subscriber.save()
        assert broker.subscribers == [subscriber]

        assert broker.topics == []
        assert mosquitto_topic.brokers == []
        mosquitto_topic.add_broker(broker.id)
        assert broker.topics == [mosquitto_topic]
        assert mosquitto_topic.brokers == [broker]

        # Can not delete a broker with subscribers.
        with pytest.raises(sqla.exc.IntegrityError):
            broker.delete()

        subscriber.delete()
        broker.delete()
        assert Broker.get_by_id(broker.id) is None

        broker.delete()  # try to delete again
        assert Broker.get_by_id(broker.id) is None

        broker.save()
        assert Broker.get_by_id(broker.id) is not None

    def test_broker_verify_consistency(self, database, broker):

        broker.protocol_version = 666
        with pytest.raises(ValueError) as exc:
            broker._verify_consistency()
            assert str(exc) == "Invalid broker protocol version!"

        broker.protocol_version = mqttc.MQTTv5
        broker.transport = "bike"
        with pytest.raises(ValueError) as exc:
            broker._verify_consistency()
            assert str(exc) == "Invalid broker transport mode!"

        broker.transport = Broker.Transport.tcp.value
        broker.use_tls = True
        with pytest.raises(ValueError) as exc:
            broker._verify_consistency()
            assert str(exc) == "Missing certificate data!"

        broker.tls_certificate = "certificate-data"
        broker.tls_version = 666
        with pytest.raises(ValueError) as exc:
            broker._verify_consistency()
            assert str(exc) == "Invalid broker TLS version!"

        broker.tls_version = ssl.PROTOCOL_TLSv1_2
        broker.tls_verifymode = 666
        with pytest.raises(ValueError) as exc:
            broker._verify_consistency()
            assert str(exc) == "Invalid broker TLS verify mode!"

    def test_broker_auth_required(
            self, database, broker, subscriber, client_id):

        broker.is_auth_required = True

        subscriber.username = "test"
        subscriber.connect(client_id)
        assert subscriber.is_connected

        subscriber.disconnect()
        assert not subscriber.is_connected

    def test_broker_tls_certificate_filepath(
            self, database, broker_tls, client_id):

        assert broker_tls._tls_cert_filename == "test.mosquitto.org.crt"
        assert broker_tls.tls_certificate_dirpath is not None
        assert broker_tls.tls_certificate_filepath.exists()
        with open(broker_tls.tls_certificate_filepath, "r") as f:
            assert f.read() == broker_tls.tls_certificate

        subscriber = Subscriber(broker_id=broker_tls.id)
        subscriber.save()  # to set all default values
        subscriber.connect(client_id)
        assert subscriber.is_connected

        subscriber.disconnect()
        assert not subscriber.is_connected

        port_backup = broker_tls.port
        broker_tls.port = 8887  # certificate expired on mosquitto test server
        with pytest.raises(ssl.SSLCertVerificationError):
            subscriber.connect(client_id)

        broker_tls.port = port_backup
        broker_tls.tls_certificate = "BAD_CERT"
        broker_tls._generate_tls_cert_file()
        with open(broker_tls.tls_certificate_filepath, "r") as f:
            assert f.read() == "BAD_CERT"
        with pytest.raises(ssl.SSLError):
            subscriber.connect(client_id)

    def test_broker_protocol_version(
            self, database, broker, subscriber, client_id):

        broker.protocol_version = mqttc.MQTTv311

        subscriber.connect(client_id)
        assert subscriber.is_connected

        subscriber.disconnect()
        assert not subscriber.is_connected

    def test_broker_websockets(
            self, database, broker, subscriber, client_id):

        broker.port = 8080
        broker.transport = Broker.Transport.websockets.value

        subscriber.connect(client_id)
        assert subscriber.is_connected

        subscriber.disconnect()
        assert not subscriber.is_connected
