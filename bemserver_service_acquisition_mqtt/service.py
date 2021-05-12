"""MQTT service"""

from pathlib import Path

from bemserver_core.database import db
from bemserver_service_acquisition_mqtt import decoders
from bemserver_service_acquisition_mqtt.model import (
    Subscriber, PayloadDecoder)
from bemserver_service_acquisition_mqtt.exceptions import ServiceError


MQTT_CLIENT_ID = "bemserver-acquisition"


class Service:
    """Acquisition service for timeseries data, based on MQTT protocol.

    :param str|Path working_dirpath:
    :param logging.logger logger: (optional, default None)
        The logger to use for the subscriber MQTT client.
    """

    def __init__(self, working_dirpath, *, logger=None):
        self._tls_cert_dirpath = Path(working_dirpath)
        self._logger = logger
        self._running_subscribers = []
        self.is_running = False

    def set_db_url(self, db_url):
        """Set database URL."""
        if (db.engine is None
                or db.engine is not None and str(db.engine.url) != db_url):
            db.set_db_url(db_url)

    def _register_decoders(self):
        for decoder_cls in decoders._PAYLOAD_DECODERS.values():
            PayloadDecoder.register_from_class(decoder_cls)

    def run(self, *, client_id=MQTT_CLIENT_ID):
        """Run the MQTT acquisition servive:
            - register payload decoders
            - get all enabled subsribers
            - connect each subscriber to its broker to get messages

        :param str client_id: (optional, default "bemserver-acquisition")
            Client ID to use, especially when using a persistent session.
        :raises ServiceError: When no enabled subscriber is available.
        """
        if self._logger is not None:
            self._logger.debug("Starting service...")

        self._register_decoders()

        rows = Subscriber.get_list(is_enabled=True)
        if len(rows) <= 0:
            raise ServiceError(
                "No subscribers available to run MQTT acquisition!")

        for row in rows:
            subscriber = row[0]
            # Set certificate file path if broker uses TLS.
            if subscriber.broker.use_tls:
                subscriber.broker.tls_certificate_dirpath = (
                    self._tls_cert_dirpath)
            # Connect subscriber.
            subscriber.connect(client_id, logger=self._logger)
            if subscriber.is_connected:
                self._running_subscribers.append(subscriber)

        self.is_running = True
        if self._logger is not None:
            self._logger.debug("Service is running!")

    def stop(self):
        """Stop the MQTT acquisition service.

        Each enabled subscriber is disconnected.
        """
        if self._logger is not None:
            self._logger.debug("Stopping service...")
        while len(self._running_subscribers) > 0:
            self._running_subscribers[0].disconnect()
            if not self._running_subscribers[0].is_connected:
                del self._running_subscribers[0]
        self.is_running = False
        if self._logger is not None:
            self._logger.debug("Service is stopped!")
