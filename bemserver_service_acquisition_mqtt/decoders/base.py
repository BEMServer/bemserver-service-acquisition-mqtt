"""MQTT generic payload decoder"""

import logging
import abc
import datetime as dt
import sqlalchemy as sqla

from bemserver_core.database import db
from bemserver_core.model import TimeseriesData
from bemserver_service_acquisition_mqtt import SERVICE_LOGNAME
from bemserver_service_acquisition_mqtt.exceptions import PayloadDecoderError


logger = logging.getLogger(SERVICE_LOGNAME)


class PayloadDecoderBase(abc.ABC):

    name = None
    description = None
    fields = []

    @property
    def _log_header(self):
        return f"[Payload decoder {self.name}]"

    def __init__(self, topic):
        self._db_topic = topic

        self.timestamp_last_reception = None

    def on_message(self, client, userdata, msg):
        # /!\ note that if message is retained, it can already be in database

        # TODO: save timestamp_last_reception in timeseries data record?
        self.timestamp_last_reception = dt.datetime.now(dt.timezone.utc)

        try:
            timestamp, values = self._decode(msg.payload)
        except PayloadDecoderError:
            # TODO: raise or log error
            pass
        else:
            self._save_to_db(timestamp, values)

    @abc.abstractmethod
    def _decode(self, raw_payload):
        logger.debug(f"{self._log_header} decoding {raw_payload}")
        return dt.datetime.now(dt.timezone.utc), {}

    def _save_to_db(self, timestamp, values):
        if self._db_topic is None:
            raise PayloadDecoderError("No topic defined to save to database!")

        logger.debug(f"{self._log_header} saving decoded data"
                     f" from topic {self._db_topic.name}")

        for topic_link in self._db_topic.links:
            if topic_link.payload_field.name not in values:
                logger.warning(
                    f"{self._log_header} no {topic_link.payload_field.name}"
                    f" value to save for topic {self._db_topic.name}!")
                continue
            tsdata = TimeseriesData(
                timeseries_id=topic_link.timeseries_id,
                timestamp=timestamp,
                value=values[topic_link.payload_field.name],
            )
            db.session.add(tsdata)
            try:
                db.session.commit()
            except sqla.exc.IntegrityError:
                db.session.rollback()
                # TODO: raise or log error
