"""Payload decoder tests"""

import pytest
import sqlalchemy as sqla

from bemserver_core.database import db
from bemserver_core.model import Timeseries
from bemserver_service_acquisition_mqtt.model import (
    PayloadDecoder, PayloadField, Topic)


class TestPayloadDecoderModel:

    def test_payload_decoder_crud(
            self, database, decoder_mosquitto_uptime_cls):

        assert PayloadDecoder.get_by_id(1) is None
        assert PayloadDecoder.get_by_name(
            decoder_mosquitto_uptime_cls.name) is None

        decoder = PayloadDecoder(name=decoder_mosquitto_uptime_cls.name)
        assert decoder.id is None
        decoder.save()
        assert decoder.id is not None
        assert decoder.name == decoder_mosquitto_uptime_cls.name
        assert decoder.description is None
        assert decoder.topics == []
        assert decoder.fields == []

        assert PayloadDecoder.get_by_id(decoder.id) == decoder
        assert PayloadDecoder.get_by_name(decoder.name) == decoder

        payload_field = decoder.add_field("temperature")
        assert isinstance(payload_field, PayloadField)
        assert decoder.fields == [payload_field]

        other_fields = []
        for i in range(2):
            new_payload_field = decoder.add_field(f"test{i}")
            assert new_payload_field in decoder.fields
            other_fields.append(new_payload_field)
        assert len(decoder.fields) == len(other_fields) + 1

        decoder.remove_field(field_id=other_fields[0].id)
        assert decoder.fields == [payload_field, other_fields[1]]

        decoder.remove_field(field_name=other_fields[1].name)
        assert decoder.fields == [payload_field]

        # Integrity error if deleting a payload decoder referenced in a topic.
        topic = Topic(name="test", payload_decoder_id=decoder.id)
        topic.save()
        with pytest.raises(sqla.exc.IntegrityError):
            decoder.delete()
        topic.delete()

        # Deleting a payload decoder also removes payload fields in cascade.
        stmt = sqla.select(PayloadField)
        stmt = stmt.filter(PayloadField.payload_decoder_id == decoder.id)
        rows = db.session.execute(stmt).all()
        assert len(rows) > 0
        decoder.delete()
        rows = db.session.execute(stmt).all()
        assert len(rows) == 0

    def test_payload_decoder_register(
            self, database, decoder_mosquitto_uptime_cls):

        assert PayloadDecoder.get_by_name(
            decoder_mosquitto_uptime_cls.name) is None

        PayloadDecoder.register_from_class(decoder_mosquitto_uptime_cls)

        decoder = PayloadDecoder.get_by_name(
            decoder_mosquitto_uptime_cls.name)
        assert decoder is not None
        assert decoder.name == decoder_mosquitto_uptime_cls.name
        assert decoder.description == decoder_mosquitto_uptime_cls.description
        assert len(decoder.fields) == 1
        assert [x.name for x in decoder.fields] == (
            decoder_mosquitto_uptime_cls.fields)


class TestPayloadFieldModel:

    def test_payload_field_crud(self, database, decoder_mosquitto_uptime_cls):

        decoder = PayloadDecoder(name=decoder_mosquitto_uptime_cls.name)
        decoder.save()

        assert PayloadField.get_by_id(1) is None
        assert PayloadField.get(decoder.id, "test") is None

        payload_field = PayloadField(
            payload_decoder_id=decoder.id, name="test")
        assert payload_field.id is None
        payload_field.save()
        assert payload_field.id is not None
        assert payload_field.payload_decoder_id == decoder.id
        assert payload_field.payload_decoder == decoder
        assert payload_field.name == "test"

        assert decoder.fields == [payload_field]

        assert PayloadField.get_by_id(payload_field.id) == payload_field
        assert PayloadField.get(
            decoder.id, payload_field.name) == payload_field

        # Unicity required on field names for each payload decoder.
        payload_field_bis = PayloadField(
            payload_decoder_id=decoder.id, name="test")
        with pytest.raises(sqla.exc.IntegrityError):
            payload_field_bis.save()

        decoder2 = PayloadDecoder(name="great_decoder")
        decoder2.save()
        payload_field2 = PayloadField(
            payload_decoder_id=decoder2.id, name="test")
        assert payload_field2 != payload_field

        payload_field.delete()
        assert PayloadField.get_by_id(1) is None
        assert PayloadField.get(decoder.id, "test") is None

    def test_payload_field_delete_cascade(
            self, database, decoder_mosquitto_uptime):

        _, decoder = decoder_mosquitto_uptime

        assert len(decoder.fields) > 0

        topic = Topic(name="test", payload_decoder_id=decoder.id)
        topic.save()
        ts = Timeseries(name="Timeseries test")
        db.session.add(ts)
        db.session.commit()
        topic.add_link(decoder.fields[0].id, ts.id)

        # Deleting payload field also removes topic links concerned in cascade.
        assert len(topic.links) == 1
        decoder.fields[0].delete()
        assert len(topic.links) == 0
