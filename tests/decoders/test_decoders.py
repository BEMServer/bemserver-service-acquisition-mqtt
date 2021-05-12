"""Decoders tests"""

import pytest
import json
import time
import datetime as dt
import sqlalchemy as sqla

from bemserver_core.database import db
from bemserver_core.model import TimeseriesData
from bemserver_service_acquisition_mqtt import decoders
from bemserver_service_acquisition_mqtt.exceptions import (
    PayloadDecoderNotFoundError)


class TestDecoders:

    def test_decoder_get_cls(self, decoder_mosquitto_uptime_cls):

        payload_decoder_cls = decoders.get_payload_decoder_cls(
            decoders.PayloadDecoderBEMServer.name)
        assert payload_decoder_cls == decoders.PayloadDecoderBEMServer

        with pytest.raises(PayloadDecoderNotFoundError):
            decoders.get_payload_decoder_cls(decoder_mosquitto_uptime_cls.name)

    def test_decoder_mosquitto_uptime_decode(
            self, mosquitto_topic, decoder_mosquitto_uptime):

        mosquitto_uptime_decoder_cls, _ = decoder_mosquitto_uptime

        mosquitto_decoder = mosquitto_uptime_decoder_cls(mosquitto_topic)
        assert mosquitto_decoder.fields == ["uptime"]

        ts_before_decode = dt.datetime.now(dt.timezone.utc)
        payload_to_decode = bytes("754369 seconds", "utf-8")
        timestamp, values = mosquitto_decoder._decode(payload_to_decode)
        ts_after_decode = dt.datetime.now(dt.timezone.utc)
        assert ts_before_decode < timestamp < ts_after_decode
        assert values["uptime"] == 754369

    def test_decoder_mosquitto_uptime_on_message(
            self, database, mosquitto_topic, subscriber):

        mosquitto_topic.add_subscriber(subscriber.id)

        # At first there is no timeseries data.
        stmt = sqla.select(TimeseriesData)
        for topic_link in mosquitto_topic.links:
            stmt = stmt.filter(
                TimeseriesData.timeseries_id == topic_link.timeseries_id
            )
        stmt = stmt.order_by(
            TimeseriesData.timestamp
        )
        tsdatas = db.session.execute(stmt).all()
        assert len(tsdatas) == 0

        ts_before_message = dt.datetime.now(dt.timezone.utc)

        # Connect the subscriber to receive messages.
        subscriber.connect()
        time.sleep(0.2)
        assert subscriber._client.is_connected()
        subscriber.subscribe_all()
        time.sleep(0.5)
        subscriber.disconnect()

        ts_after_message = dt.datetime.now(dt.timezone.utc)
        ts_last_recept = (
            mosquitto_topic.payload_decoder_instance.timestamp_last_reception)
        assert ts_before_message < ts_last_recept < ts_after_message

        # A retained message has been received and stored as timeseries in DB.
        tsdatas = db.session.execute(stmt).all()
        assert len(tsdatas) >= 1
        tsdata = tsdatas[0][0]

        assert tsdata.timeseries_id in [
            x.timeseries_id for x in mosquitto_topic.links]

    def test_decoder_bemserver_decode(self):

        bemserver_decoder = decoders.PayloadDecoderBEMServer(None)
        assert bemserver_decoder.fields == ["value"]

        ts_now = dt.datetime.now(dt.timezone.utc)
        payload_to_decode = {
            "ts": ts_now.isoformat(),
            "value": 66.6,
        }
        ts, values = bemserver_decoder._decode(json.dumps(payload_to_decode))
        assert ts == ts_now
        assert values["value"] == payload_to_decode["value"]

    def test_decoder_chirpstack_decode(self):

        timestamp = dt.datetime(
            2021, 5, 3, 17, 28, 55, 41898, tzinfo=dt.timezone.utc)

        chirpstack_decoder = decoders.PayloadDecoderChirpstackARF8200AA(None)
        assert chirpstack_decoder.fields == ["channelA", "channelB"]
        payload_to_decode = {
            "rxInfo": [
                {
                    "time": "2021-05-03T17:28:55.041898Z",
                },
            ],
            "objectJSON": {
                "channelA": {
                    "unit": "mA",
                    "value": 4.126,
                },
                "channelB": {
                    "unit": "mA",
                    "value": 4.131,
                },
            },
        }
        ts, values = chirpstack_decoder._decode(json.dumps(payload_to_decode))
        assert ts == timestamp
        assert values == {
            "channelA": 4.126,
            "channelB": 4.131,
        }

        chirpstack_decoder = decoders.PayloadDecoderChirpstackEM300TH868(None)
        assert chirpstack_decoder.fields == ["temperature", "humidity"]
        payload_to_decode["objectJSON"] = {
            "humidity": 0,
            "temperature": 21,
        }
        ts, values = chirpstack_decoder._decode(json.dumps(payload_to_decode))
        assert ts == timestamp
        assert values == {
            "temperature": 21,
            "humidity": 0,
        }

        chirpstack_decoder = decoders.PayloadDecoderChirpstackUC11(None)
        assert chirpstack_decoder.fields == ["temperature", "humidity"]
        ts, values = chirpstack_decoder._decode(json.dumps(payload_to_decode))
        assert ts == timestamp
        assert values == {
            "temperature": 21,
            "humidity": 0,
        }

        chirpstack_decoder = decoders.PayloadDecoderChirpstackEAGLE1500(None)
        assert chirpstack_decoder.fields == [
            "active_power", "current", "export_active_energy",
            "import_active_energy", "power_factor", "reactive_energy",
            "relay_state", "voltage"
        ]
        payload_to_decode["objectJSON"] = {
            "active_power": 0,
            "current": 0,
            "export_active_energy": 0,
            "import_active_energy": 27581,
            "power_factor": 0,
            "reactive_energy": 588,
            "relay_state": 1,
            "voltage": 234.61,
        }
        ts, values = chirpstack_decoder._decode(json.dumps(payload_to_decode))
        assert ts == timestamp
        assert values == {
            "active_power": 0,
            "current": 0,
            "export_active_energy": 0,
            "import_active_energy": 27581,
            "power_factor": 0,
            "reactive_energy": 588,
            "relay_state": 1,
            "voltage": 234.61,
        }
