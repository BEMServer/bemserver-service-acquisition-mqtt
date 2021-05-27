"""Decoder for Chirpstack payloads"""

import json
import datetime as dt

from .base import PayloadDecoderBase
from bemserver_service_acquisition_mqtt.exceptions import PayloadDecoderError


class PayloadDecoderChirpstackBase(PayloadDecoderBase):

    def _decode(self, raw_payload):
        timestamp, _ = super()._decode(raw_payload)
        try:
            json_payload = json.loads(raw_payload)
        except json.decoder.JSONDecodeError as exc:
            raise PayloadDecoderError(str(exc))
        # example: 2021-04-16T14:03:13.432986Z
        timestamp = dt.datetime.fromisoformat(
            json_payload["rxInfo"][0]["time"].replace("Z", "+00:00"))
        data = json_payload.get("objectJSON", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.decoder.JSONDecodeError as exc:
                raise PayloadDecoderError(str(exc))
        return timestamp, self._decode_values(data)

    def _decode_values(self, data):
        return {
            field: data[field] for field in self.fields if field in data
        }


class PayloadDecoderChirpstackARF8200AA(PayloadDecoderChirpstackBase):

    name = "chirpstack_ARF8200AA"
    description = "Chirpstack payload decoder for ARF8200AA devices"
    fields = ["channelA", "channelB"]

    def _decode_values(self, data):
        return {
            field: data[field]["value"] for field in self.fields
            if field in data and "value" in data[field]
        }


class PayloadDecoderChirpstackEM300TH868(PayloadDecoderChirpstackBase):

    name = "chirpstack_EM300-TH-868"
    description = "Chirpstack payload decoder for EM300-TH-868 devices"
    fields = ["temperature", "humidity"]


class PayloadDecoderChirpstackUC11(PayloadDecoderChirpstackEM300TH868):

    name = "chirpstack_UC11"
    description = "Chirpstack payload decoder for UC11 devices"


class PayloadDecoderChirpstackEAGLE1500(PayloadDecoderChirpstackBase):

    name = "chirpstack_EAGLE1500"
    description = "Chirpstack payload decoder for EAGLE 1500(80) devices"
    fields = [
        "active_power", "current", "export_active_energy",
        "import_active_energy", "power_factor", "reactive_energy",
        "relay_state", "voltage"
    ]
