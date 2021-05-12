"""MQTT payload decoder"""

import logging
import sqlalchemy as sqla

from bemserver_core.database import Base, BaseMixin, db
from bemserver_service_acquisition_mqtt import decoders, SERVICE_LOGNAME
from bemserver_service_acquisition_mqtt.exceptions import (
    PayloadDecoderRegistrationError)


logger = logging.getLogger(SERVICE_LOGNAME)


class PayloadField(Base, BaseMixin):
    """Describers the fields of each payload.

    :param int payload_decoder_id: Relation to a payload decoder unique ID.
    :param str name: Field name in payload.
    """
    __tablename__ = "mqtt_payload_field"
    __table_args__ = (
        sqla.UniqueConstraint("payload_decoder_id", "name"),
    )

    id = sqla.Column(sqla.Integer, primary_key=True)
    payload_decoder_id = sqla.Column(
        sqla.Integer,
        sqla.ForeignKey("mqtt_payload_decoder.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = sqla.Column(sqla.String(80), nullable=False)

    payload_decoder = sqla.orm.relationship(
        "PayloadDecoder", back_populates="fields")

    topic_links = sqla.orm.relationship(
        "TopicLink", back_populates="payload_field", cascade="all,delete",
        passive_deletes=True)

    @classmethod
    def get(cls, payload_decoder_id, field_name):
        """Find in database a payload field by its name and payload decoder ID.

        :param int payload_decoder_id:
            Unique ID of the payload decoder related to the field.
        :param str field_name: Unique field name to find.
        :returns PayloadField: Instance found of `PayloadField`.
        """
        stmt = sqla.select(cls)
        stmt = stmt.filter(cls.payload_decoder_id == payload_decoder_id)
        stmt = stmt.filter(cls.name == field_name)
        try:
            return db.session.execute(stmt).one()[0]
        except sqla.exc.NoResultFound:
            return None


class PayloadDecoder(Base, BaseMixin):
    """Decribes a payload decoder, with the fields it contains.

    :param str name: Unique name of payload decoder.
    :param str description: (optional, default None)
        Text to describe the payload decoder.
    """
    __tablename__ = "mqtt_payload_decoder"

    id = sqla.Column(sqla.Integer, primary_key=True)
    name = sqla.Column(sqla.String(250), unique=True, nullable=False)
    description = sqla.Column(sqla.String(250))

    topics = sqla.orm.relationship("Topic", back_populates="payload_decoder")
    fields = sqla.orm.relationship(
        "PayloadField", back_populates="payload_decoder", cascade="all,delete",
        passive_deletes=True)

    def add_field(self, field_name):
        """Add a payload field to this payload decoder.

        :param str field_name: Unique field name (for this decoder).
        :returns PayloadField: Instance of created `PayloadField`.
        """
        field = PayloadField(payload_decoder_id=self.id, name=field_name)
        field.save()
        return field

    def remove_field(self, *, field_id=None, field_name=None):
        """Remove a payload field from this payload decoder.

        Payload decoder field can be removed using its unique ID or name.

        :param int field_id: (optional, default None)
            Unique field ID used to find the payload field to remove.
        :param str field_name: (optional, default None)
            Unique field name used to find the payload field to remove.
        :raises ValueError: When both field ID and name are not defined.
        """
        if field_id is not None:
            field = PayloadField.get_by_id(field_id)
        elif field_name is not None:
            field = PayloadField.get(self.id, field_name)
        else:
            raise ValueError("Missing either field_id or field_name!")
        if field in self.fields:
            field.delete()

    @classmethod
    def register_from_class(cls, decoder_cls):
        """Register a new payload decoder (with fields) in database.

        :param PayloadDecoderBase decoder_cls:
            Payload decoder class to register in database.
        :raises PayloadDecoderRegistrationError:
            When payload decoder class is not valid.
        :returns PayloadDecoder: Instance of registered `PayloadDecoder`.
        """
        logger.info(f"Registering {decoder_cls} payload decoder...")
        if not issubclass(decoder_cls, decoders.PayloadDecoderBase):
            msg_err = (
                f"{decoder_cls} does not subclass"
                f" {decoders.PayloadDecoderBase}!")
            logger.error(msg_err)
            raise PayloadDecoderRegistrationError(msg_err)
        # Verify if decoder exists in database. If not insert it.
        decoder = cls.get_by_name(decoder_cls.name)
        if decoder is None:
            decoder = cls(
                name=decoder_cls.name, description=decoder_cls.description)
            decoder.save()
            for field in decoder_cls.fields:
                decoder.add_field(field)
        # TODO: if exists, try to update (description, add/remove fields)?
        logger.info(f"{decoder_cls.name} payload decoder registered!")
        return decoder

    @classmethod
    def get_by_name(cls, name):
        """Find a subscriber by its unique name stored in database.

        :param str name: Unique name of the payload decoder to find.
        :returns PayloadDecoder: Instance found of `PayloadDecoder`.
        """
        # Verfify that `name` exists to avoid a warning.
        if name is None:
            return None
        stmt = sqla.select(cls).filter(cls.name == name)
        try:
            return db.session.execute(stmt).one()[0]
        except sqla.exc.NoResultFound:
            return None
