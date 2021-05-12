"""Decoder for Chirpstack payloads"""

import abc
import json
import datetime as dt

from .base import PayloadDecoderBase


class PayloadDecoderChirpstackBase(PayloadDecoderBase):

    def _decode(self, raw_payload):
        json_payload = json.loads(raw_payload)
        # example: 2021-04-16T14:03:13.432986Z
        timestamp = dt.datetime.fromisoformat(
            json_payload["rxInfo"][0]["time"].replace("Z", "+00:00"))
        return timestamp, self._decode_values(json_payload)

    @abc.abstractmethod
    def _decode_values(self, json_payload):
        return {}


class PayloadDecoderChirpstackARF8200AA(PayloadDecoderChirpstackBase):

    name = "chirpstack_ARF8200AA"
    description = "Chirpstack payload decoder for ARF8200AA devices"
    fields = ["channelA", "channelB"]

    def _decode_values(self, json_payload):
        data = json_payload["objectJSON"]
        return {
            "channelA": data["channelA"]["value"],
            "channelB": data["channelB"]["value"],
        }


class PayloadDecoderChirpstackEM300TH868(PayloadDecoderChirpstackBase):

    name = "chirpstack_EM300-TH-868"
    description = "Chirpstack payload decoder for EM300-TH-868 devices"
    fields = ["temperature", "humidity"]

    def _decode_values(self, json_payload):
        return {
            "temperature": json_payload["objectJSON"]["temperature"],
            "humidity": json_payload["objectJSON"]["humidity"],
        }


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

    def _decode_values(self, json_payload):
        data = json_payload["objectJSON"]
        return {
            "active_power": data["active_power"],
            "current": data["current"],
            "export_active_energy": data["export_active_energy"],
            "import_active_energy": data["import_active_energy"],
            "power_factor": data["power_factor"],
            "reactive_energy": data["reactive_energy"],
            "relay_state": data["relay_state"],
            "voltage": data["voltage"],
        }
