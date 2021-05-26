"""Global conftest"""

import ssl
import json
import uuid
import datetime as dt
from pathlib import Path

import paho.mqtt.client as mqttc
from bemserver_core.database import db
from bemserver_core import model as core_model
from bemserver_core.testutils import setup_db

import pytest
from pytest_postgresql import factories as ppf

from bemserver_service_acquisition_mqtt import model as svc_model, decoders
from bemserver_service_acquisition_mqtt.service import MQTT_CLIENT_ID


_BROKER_CERTIFICATE = """
-----BEGIN CERTIFICATE-----
MIIEAzCCAuugAwIBAgIUBY1hlCGvdj4NhBXkZ/uLUZNILAwwDQYJKoZIhvcNAQEL
BQAwgZAxCzAJBgNVBAYTAkdCMRcwFQYDVQQIDA5Vbml0ZWQgS2luZ2RvbTEOMAwG
A1UEBwwFRGVyYnkxEjAQBgNVBAoMCU1vc3F1aXR0bzELMAkGA1UECwwCQ0ExFjAU
BgNVBAMMDW1vc3F1aXR0by5vcmcxHzAdBgkqhkiG9w0BCQEWEHJvZ2VyQGF0Y2hv
by5vcmcwHhcNMjAwNjA5MTEwNjM5WhcNMzAwNjA3MTEwNjM5WjCBkDELMAkGA1UE
BhMCR0IxFzAVBgNVBAgMDlVuaXRlZCBLaW5nZG9tMQ4wDAYDVQQHDAVEZXJieTES
MBAGA1UECgwJTW9zcXVpdHRvMQswCQYDVQQLDAJDQTEWMBQGA1UEAwwNbW9zcXVp
dHRvLm9yZzEfMB0GCSqGSIb3DQEJARYQcm9nZXJAYXRjaG9vLm9yZzCCASIwDQYJ
KoZIhvcNAQEBBQADggEPADCCAQoCggEBAME0HKmIzfTOwkKLT3THHe+ObdizamPg
UZmD64Tf3zJdNeYGYn4CEXbyP6fy3tWc8S2boW6dzrH8SdFf9uo320GJA9B7U1FW
Te3xda/Lm3JFfaHjkWw7jBwcauQZjpGINHapHRlpiCZsquAthOgxW9SgDgYlGzEA
s06pkEFiMw+qDfLo/sxFKB6vQlFekMeCymjLCbNwPJyqyhFmPWwio/PDMruBTzPH
3cioBnrJWKXc3OjXdLGFJOfj7pP0j/dr2LH72eSvv3PQQFl90CZPFhrCUcRHSSxo
E6yjGOdnz7f6PveLIB574kQORwt8ePn0yidrTC1ictikED3nHYhMUOUCAwEAAaNT
MFEwHQYDVR0OBBYEFPVV6xBUFPiGKDyo5V3+Hbh4N9YSMB8GA1UdIwQYMBaAFPVV
6xBUFPiGKDyo5V3+Hbh4N9YSMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQEL
BQADggEBAGa9kS21N70ThM6/Hj9D7mbVxKLBjVWe2TPsGfbl3rEDfZ+OKRZ2j6AC
6r7jb4TZO3dzF2p6dgbrlU71Y/4K0TdzIjRj3cQ3KSm41JvUQ0hZ/c04iGDg/xWf
+pp58nfPAYwuerruPNWmlStWAXf0UTqRtg4hQDWBuUFDJTuWuuBvEXudz74eh/wK
sMwfu1HFvjy5Z0iMDU8PUDepjVolOCue9ashlS4EB5IECdSR2TItnAIiIwimx839
LdUdRudafMu5T5Xma182OC0/u/xRlEm+tvKGGmfFcN0piqVl8OrSPBgIlb+1IKJE
m/XriWr/Cq4h/JfB7NTsezVslgkBaoU=
-----END CERTIFICATE-----
"""


postgresql_proc = ppf.postgresql_proc(
    postgres_options="-c shared_preload_libraries='timescaledb'"
)
postgresql = ppf.postgresql('postgresql_proc')


@pytest.fixture
def database(postgresql):
    yield from setup_db(postgresql)


@pytest.fixture(params=[{}])
def timeseries_data(request, database):

    param = request.param

    nb_ts = param.get("nb_ts", 1)
    nb_tsd = param.get("nb_tsd", 24 * 100)

    ts_l = []

    for i in range(nb_ts):
        ts_i = core_model.Timeseries(
            name=f"Timeseries {i}",
            description=f"Test timeseries #{i}",
        )
        db.session.add(ts_i)

        start_dt = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        for i in range(nb_tsd):
            timestamp = start_dt + dt.timedelta(hours=i)
            db.session.add(
                core_model.TimeseriesData(
                    timestamp=timestamp,
                    timeseries=ts_i,
                    value=i
                )
            )

        ts_l.append(ts_i)

    db.session.commit()

    return [
        (ts.id, nb_tsd, start_dt, start_dt + dt.timedelta(hours=nb_tsd))
        for ts in ts_l
    ]


@pytest.fixture
def decoder_mosquitto_uptime_cls():

    class PayloadDecoderMosquittoUptime(decoders.base.PayloadDecoderBase):
        name = "mosquitto_uptime_test"
        fields = ["uptime"]

        def _decode(self, raw_payload):
            timestamp = dt.datetime.now(dt.timezone.utc)
            raw_value = str(raw_payload, "utf-8")
            values = {
                "uptime": float(raw_value.split(" ")[0]),
            }
            return timestamp, values

    return PayloadDecoderMosquittoUptime


@pytest.fixture
def decoder_mosquitto_uptime(database, decoder_mosquitto_uptime_cls):
    db_decoder = svc_model.PayloadDecoder.register_from_class(
        decoder_mosquitto_uptime_cls)
    decoders._PAYLOAD_DECODERS[
        decoder_mosquitto_uptime_cls.name] = decoder_mosquitto_uptime_cls
    return decoder_mosquitto_uptime_cls, db_decoder


@pytest.fixture
def broker(database):
    broker = svc_model.Broker(host="test.mosquitto.org", port=1883)
    broker.save()
    return broker


@pytest.fixture
def broker_tls(database, tmpdir):
    broker = svc_model.Broker(
        host="test.mosquitto.org", port=8883,
        use_tls=True, tls_certificate=_BROKER_CERTIFICATE,
        tls_verifymode=ssl.CERT_REQUIRED)
    broker.save()
    broker.tls_certificate_dirpath = Path(str(tmpdir))
    return broker


@pytest.fixture
def subscriber(broker):
    subscriber = svc_model.Subscriber(broker_id=broker.id)
    subscriber.save()
    return subscriber


@pytest.fixture
def subscriber_tls(broker_tls):
    subscriber = svc_model.Subscriber(broker_id=broker_tls.id)
    subscriber.save()
    return subscriber


@pytest.fixture
def client_id():
    return f"{MQTT_CLIENT_ID}-test-{uuid.uuid4()}"


@pytest.fixture
def mosquitto_topic_name():
    return "$SYS/broker/uptime"


@pytest.fixture
def topic_name():
    return "bemserver/test/1"


@pytest.fixture
def mosquitto_topic(mosquitto_topic_name, decoder_mosquitto_uptime):
    _, decoder = decoder_mosquitto_uptime
    topic = svc_model.Topic(
        name=mosquitto_topic_name, payload_decoder_id=decoder.id)
    topic.save()
    for payload_field in decoder.fields:
        ts = core_model.Timeseries(
            name=f"Timeseries mosquitto {payload_field.name}")
        db.session.add(ts)
        db.session.commit()
        topic.add_link(payload_field.id, ts.id)
    return topic


@pytest.fixture
def topic(topic_name):
    decoder = svc_model.PayloadDecoder.register_from_class(
        decoders.PayloadDecoderBEMServer)
    topic = svc_model.Topic(
        name=topic_name, payload_decoder_id=decoder.id)
    topic.save()
    for payload_field in decoder.fields:
        ts = core_model.Timeseries(
            name=f"Timeseries bemserver test {payload_field.name}")
        db.session.add(ts)
        db.session.commit()
        topic.add_link(payload_field.id, ts.id)
    return topic


@pytest.fixture
def publisher(topic_name):
    pub_cli = mqttc.Client(
        protocol=mqttc.MQTTv5,
        transport=svc_model.Broker.Transport.tcp.value)
    pub_cli.connect(host="test.mosquitto.org", port=1883)
    pub_cli.loop_start()

    # Set a retain message for "bemserver/test/1" topic.
    payload = {
        "ts": dt.datetime(
            2021, 4, 27, 16, 5, 11, tzinfo=dt.timezone.utc).isoformat(),
        "value": 42,
    }
    msg_info = pub_cli.publish(
        topic=topic_name, payload=json.dumps(payload), qos=1, retain=True)
    msg_info.wait_for_publish()

    yield pub_cli

    # Delete the retained message.
    msg_info = pub_cli.publish(
        topic=topic_name, payload=None, qos=1, retain=True)
    msg_info.wait_for_publish()

    pub_cli.loop_stop()
    pub_cli.disconnect()


@pytest.fixture
def db_url():
    """Dummy but realistic DB URL for the tests"""
    return "postgresql+psycopg2://user:password@localhost:5432/bemserver-test"


@pytest.fixture
def json_service_config(db_url, tmpdir):
    return {
        "db_url": db_url,
        "working_dirpath": str(tmpdir),
        "logging": {
            "enabled": True,
            "format": (
                "%(asctime)s %(levelname)-8s"
                " [%(name)s].[%(filename)s:%(funcName)s:%(lineno)d]"
                " [%(processName)s:%(process)d].[%(threadName)s:%(thread)d]"
                " || %(message)s"),
            "level": "DEBUG",
            "dirpath": str(tmpdir),
            "history": 30,
        },
    }
