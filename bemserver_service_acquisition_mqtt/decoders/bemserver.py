"""Decoder for BEMServer payloads"""

import json
import datetime as dt

from .base import PayloadDecoderBase
from bemserver_service_acquisition_mqtt.exceptions import PayloadDecoderError


class PayloadDecoderBEMServer(PayloadDecoderBase):

    name = "bemserver"
    description = "Default BEMServer payload decoder"
    fields = ["value"]

    def _decode(self, raw_payload):
        timestamp, values = super()._decode(raw_payload)
        try:
            json_payload = json.loads(raw_payload)
        except json.decoder.JSONDecodeError as exc:
            raise PayloadDecoderError(str(exc))
        timestamp = dt.datetime.fromisoformat(
            json_payload["ts"].replace("Z", "+00:00"))
        if "value" in json_payload:
            values["value"] = float(json_payload["value"])
        return timestamp, values
