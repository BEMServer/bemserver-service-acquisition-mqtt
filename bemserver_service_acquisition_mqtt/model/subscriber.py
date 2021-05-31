"""MQTT subscriber"""

import logging
import time
import datetime as dt
import sqlalchemy as sqla
import paho.mqtt.client as mqttc
import paho.mqtt.properties as mqtt_props

from bemserver_core.database import Base, BaseMixin, db
from bemserver_service_acquisition_mqtt import SERVICE_LOGNAME
from bemserver_service_acquisition_mqtt.model import Broker


logger = logging.getLogger(SERVICE_LOGNAME)


class Subscriber(Base, BaseMixin):
    """The scubscriber describe how to connect to a broker.

    Subscriber client waits for messages as soon as it is connected.
    Subscriptions to topics must be done manually, calling `subscribe_all`
    (which automatically subscribes to all topics wanted by the subscriber) or
    `subscribe` (to a specific topic) methods. Same for unsubscriptions.

    :param bool is_enabled: (default True)
        To disable a subscriber client. Allows to not use it without deletion.
    :param int keep_alive: (default 60)
        Time interval, in seconds, to auto-check client connection status.
    :param bool use_persistent_session: (default True)
        If True makes client session persistent even after its disconnection.
        For this, subscriber's `client_id` is required when connecting.
        A persistent session keeps in memory which topics are subscribed and
        which messages have been received or not (also requires QoS>1).
    :param int session_expiry: (default 3600)
        Time, in seconds, to keep client session after its disconnection.
        (useless if session is not persistent)
    :param str description: (optional, default None)
        Text to describe the subscriber.
    :param str username: (optional, default None)
        Username that authenticates subscriber with the broker, if required.
    :param str password: (optional, default None)
        Password that authenticates subscriber with the broker, if required.
    :param int broker_id: Relation to a broker unique ID.
    :param bool is_connected: (optional, default False)
        Field auto-updated by `connect` and `disconnect` methods.
        This allows to known the last client connection status.
    :param datetime timestamp_last_connection: (optional, default None)
        Field auto-updated by `connect` and `disconnect` methods.
        This allows to known the last client connection timestamp.
    """
    __tablename__ = "mqtt_subscriber"

    id = sqla.Column(sqla.Integer, primary_key=True)
    is_enabled = sqla.Column(sqla.Boolean, nullable=False, default=True)
    keep_alive = sqla.Column(sqla.Integer, nullable=False, default=60)
    use_persistent_session = sqla.Column(
        sqla.Boolean, nullable=False, default=True)
    session_expiry = sqla.Column(sqla.Integer, nullable=False, default=3600)
    description = sqla.Column(sqla.String(250))
    username = sqla.Column(sqla.String)
    password = sqla.Column(sqla.String)
    broker_id = sqla.Column(
        sqla.Integer,
        sqla.ForeignKey('mqtt_broker.id'),
        nullable=False,
    )
    is_connected = sqla.Column(sqla.Boolean, nullable=False, default=False)
    timestamp_last_connection = sqla.Column(sqla.DateTime(timezone=True))

    broker = sqla.orm.relationship("Broker", back_populates="subscribers")
    topics = sqla.orm.relationship(
        "Topic", secondary="mqtt_topic_by_subscriber",
        back_populates="subscribers")

    @property
    def must_authenticate(self):
        return self.broker.is_auth_required and self.username is not None

    @property
    def _log_header(self):
        return f"[Subscriber #{self.id} @{self.broker.host}]"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_on_load()

    @sqla.orm.reconstructor
    def _init_on_load(self):
        self._client_id = None
        self._client = None
        self._client_session_present = False

    def _client_create(self):
        # Initialize paho MQTT client.
        logger.debug(f"{self._log_header} creating MQTT client...")
        client_kwargs = {
            "protocol": self.broker.protocol_version,
            "transport": self.broker.transport,
        }
        if self._client_id is not None:
            client_kwargs["client_id"] = self._client_id
        if self.broker.protocol_version in (mqttc.MQTTv31, mqttc.MQTTv311,):
            client_kwargs["clean_session"] = not self.use_persistent_session
        logger.debug(
            f"{self._log_header} MQTT client parameters: {client_kwargs}")
        client = mqttc.Client(**client_kwargs)
        # Set client callbacks.
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_subscribe = self._on_subscribe
        client.on_unsubscribe = self._on_unsubscribe
        client.on_log = self._on_log
        return client

    def _client_apply_security(self):
        # Apply MQTT security (authentication, TLS...).
        logger.debug(f"{self._log_header} applying security on MQTT client...")
        logger.debug(f"{self._log_header} MQTT client authentication"
                     f" {'' if self.must_authenticate else 'NOT '}required")
        if self.must_authenticate:
            self._client.username_pw_set(self.username, password=self.password)
        logger.debug(f"{self._log_header} MQTT client TLS cert"
                     f" {'' if self.broker.use_tls else 'NOT '}required")
        if self.broker.use_tls:
            self._client.tls_set(
                ca_certs=self.broker.tls_certificate_filepath,
                cert_reqs=self.broker.tls_verifymode,
                tls_version=self.broker.tls_version)

    def _client_connect(self):
        logger.debug(f"{self._log_header} connecting MQTT client...")
        # Set client connection properties.
        cli_conn_kwargs = {
            "host": self.broker.host,
            "port": self.broker.port,
            "keepalive": self.keep_alive,
        }
        if self.broker.protocol_version == mqttc.MQTTv5:
            cli_conn_kwargs["clean_start"] = not self.use_persistent_session
            conn_props = mqtt_props.Properties(mqtt_props.PacketTypes.CONNECT)
            conn_props.SessionExpiryInterval = self.session_expiry
            cli_conn_kwargs["properties"] = conn_props
        # Connect the client.
        self._client.connect(**cli_conn_kwargs)
        # TODO: raise or log errors

    def connect(self, client_id=None, *, logger=None):
        """Instantiate the MQTT client and connect it to its broker.

        :param str client_id: (optional, default None)
            Client ID to use, especially when using a persistent session.
        :param logging.Logger logger: (optional, default None)
            The logger to use for subscriber MQTT client.
        :raises ssl.SSLError: When TLS certificate is not valid.
        :raises ssl.SSLCertVerificationError: When TLS certificate expired.
        """
        self._client_id = client_id
        self._client = self._client_create()
        self._client.enable_logger(logger)
        self._client_apply_security()
        self._client_connect()

        # It is important that subscriptions occurs before starting the
        #  waiting messages loop in order to receive stored messages for
        #  a persistent session.
        self.subscribe_all()
        # Run a threaded interface to the network loop in the background.
        #  (messages are received in this loop)
        self._client.loop_start()

        # TODO: Improve this in case to avoid infinite loop.
        # Wait for the connection to be effective.
        while (not self._client.is_connected()):
            time.sleep(0.1)
        self.is_connected = True
        self.timestamp_last_connection = dt.datetime.now(dt.timezone.utc)
        self.save()

    def _on_connect(
            self, client, userdata, flags, reasonCode, properties=None):
        # /!\ MQTTv3 and MQTTv5 do not set reasonCode value the same way...
        reason_code = reasonCode
        if isinstance(reasonCode, mqttc.ReasonCodes):
            reason_code = reasonCode.value
        if reason_code != 0:
            # TODO: raise error?
            logger.error(
                f"{self._log_header} connection error reason: "
                f"{mqttc.connack_string(reason_code)}")

        self._client_session_present = bool(flags.get("session present", 0))

        # TODO: publish message on subscriber client status topic (->online)?

    def disconnect(self):
        """Disconnect the MQTT client from its broker."""
        # At each disconnection, client subscriptions are lost event when
        #  persistent session is used. Persistent session just means that
        #  broker will keep messages for the subscriber when it reconnects
        #  and re-subscribes to those topics.
        # Update topics' subscription states in database.
        for topic in self.topics:
            topic.update_subscription(self.id, False)

        self._client.disconnect()
        self._client.disable_logger()

        # TODO: Improve this in case to avoid infinite loop.
        # Wait for the disconnection to be effective.
        while (self._client.is_connected()):
            time.sleep(0.1)
        self.is_connected = False
        self.save()

        # Kill the network loop that receives messages.
        self._client.loop_stop()

    def _on_disconnect(self, client, userdata, reasonCode, properties=None):
        if reasonCode != 0:
            logger.error(
                f"{self._log_header} disconnection error reason: "
                f"{mqttc.connack_string(reasonCode)}")

        # TODO: publish message on subscriber client status topic (->offline)?

    def subscribe(self, topic):
        """Make the MQTT client subscribe to the defined topic.

        :param Topic topic: Topic instance to subscribe to.
        """
        self._client.message_callback_add(
            topic.name, topic.payload_decoder_instance.on_message)
        self._client.subscribe(topic.name, topic.qos)
        topic.update_subscription(self.id, True)

    def subscribe_all(self):
        """Automatically make the MQTT client subscribe to all its topics."""
        logger.info(f"{self._log_header} subscribing to all topics"
                    f" ({len(self.topics)})...")
        for topic in self.topics:
            self.subscribe(topic)

    def _on_subscribe(
            self, client, userdata, mid, granted_qos, properties=None):
        pass

    def unsubscribe(self, topic):
        """Make the MQTT client unsubscribe from the defined topic.

        :param Topic topic: Topic instance to unsubscribe from.
        """
        self._client.unsubscribe(topic.name)
        topic.update_subscription(self.id, False)

    def unsubscribe_all(self):
        """Automatically make the MQTT client unsubscribe from all its topics.
        """
        logger.info(f"{self._log_header} unsubscribing from all topics"
                    f" ({len(self.topics)})...")
        for topic in self.topics:
            self.unsubscribe(topic)

    def _on_unsubscribe(self, client, userdata, mid, properties, reasonCode):
        pass

    def _on_log(self, client, userdata, level, buf):
        pass

    def _verify_consistency(self):
        broker = Broker.get_by_id(self.broker_id)
        if broker.is_auth_required:
            if self.username is None:
                raise ValueError("Broker requires username authentication!")
        elif self.username is not None:
            logger.warning(
                f"{self._log_header} authentication data (username...)"
                " is useless as broker do not require it.")

    @classmethod
    def get_list(cls, is_enabled=None):
        """List all subscribers stored in database.

        :param bool is_enabled: (optional, default None)
            Filter subscribers on `is_enabled` field value. Ignored if `None`.
        :returns list: The list of subscribers found.
        """
        stmt = sqla.select(cls)
        if is_enabled is not None:
            stmt = stmt.filter(cls.is_enabled == is_enabled)
        stmt = stmt.order_by(cls.id)
        return db.session.execute(stmt).all()
