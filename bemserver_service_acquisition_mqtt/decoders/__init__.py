"""MQTT payload decoders"""

from bemserver_service_acquisition_mqtt.exceptions import (
    PayloadDecoderNotFoundError,
)

from .base import PayloadDecoderBase  # noqa
from .bemserver import PayloadDecoderBEMServer
from .chirpstack import (
    PayloadDecoderChirpstackARF8200AA, PayloadDecoderChirpstackEM300TH868,
    PayloadDecoderChirpstackUC11, PayloadDecoderChirpstackEAGLE1500)


_PAYLOAD_DECODERS = {
    x.name: x for x in [
        PayloadDecoderBEMServer,
        PayloadDecoderChirpstackARF8200AA,
        PayloadDecoderChirpstackEM300TH868,
        PayloadDecoderChirpstackUC11,
        PayloadDecoderChirpstackEAGLE1500,
    ]
}


def get_payload_decoder_cls(payload_decoder_name):
    """Get a registered payload decoder class from its name.

    :param str payload_decoder_name: Name of decoder to find.
    :returns PayloadDecoderBase: Payload decoder class found.
    :raises PayloadDecoderNotFoundError:
        When payload decoder class does not exist.
    """
    try:
        return _PAYLOAD_DECODERS[payload_decoder_name]
    except KeyError:
        raise PayloadDecoderNotFoundError(
            f"{payload_decoder_name} decoder not found!")
