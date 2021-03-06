import io
import json
import os
import threading

from typing import Any, Optional, IO

from platypush.message import Message
from platypush.plugins import Plugin, action


class MqttPlugin(Plugin):
    """
    This plugin allows you to send custom message to a message queue compatible
    with the MQTT protocol, see http://mqtt.org/

    Requires:

        * **paho-mqtt** (``pip install paho-mqtt``)

    """

    def __init__(self, host=None, port=1883, tls_cafile=None,
                 tls_certfile=None, tls_keyfile=None,
                 tls_version=None, tls_ciphers=None, username=None,
                 password=None, **kwargs):
        """
        :param host: If set, MQTT messages will by default routed to this host unless overridden in `send_message` (default: None)
        :type host: str

        :param port: If a default host is set, specify the listen port (default: 1883)
        :type port: int

        :param tls_cafile: If a default host is set and requires TLS/SSL, specify the certificate authority file (default: None)
        :type tls_cafile: str

        :param tls_certfile: If a default host is set and requires TLS/SSL, specify the certificate file (default: None)
        :type tls_certfile: str

        :param tls_keyfile: If a default host is set and requires TLS/SSL, specify the key file (default: None)
        :type tls_keyfile: str

        :param tls_version: If a default host is set and requires TLS/SSL, specify the minimum TLS supported version (default: None)
        :type tls_version: str

        :param tls_ciphers: If a default host is set and requires TLS/SSL, specify the supported ciphers (default: None)
        :type tls_ciphers: str

        :param username: If a default host is set and requires user authentication, specify the username ciphers (default: None)
        :type username: str

        :param password: If a default host is set and requires user authentication, specify the password ciphers (default: None)
        :type password: str
        """

        super().__init__(**kwargs)

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.tls_cafile = os.path.abspath(os.path.expanduser(tls_cafile)) \
            if tls_cafile else None

        self.tls_certfile = os.path.abspath(os.path.expanduser(tls_certfile)) \
            if tls_certfile else None

        self.tls_keyfile = os.path.abspath(os.path.expanduser(tls_keyfile)) \
            if tls_keyfile else None

        self.tls_version = tls_version
        self.tls_ciphers = tls_ciphers

    @action
    def publish(self, topic: str, msg: Any, host: Optional[str] = None, port: int = 1883,
                reply_topic: Optional[str] = None, timeout: int = 60,
                tls_cafile: Optional[str] = None, tls_certfile: Optional[str] = None,
                tls_keyfile: Optional[str] = None, tls_version: Optional[str] = None,
                tls_ciphers: Optional[str] = None, username: Optional[str] = None,
                password: Optional[str] = None):
        """
        Sends a message to a topic.

        :param topic: Topic/channel where the message will be delivered
        :param msg: Message to be sent. It can be a list, a dict, or a Message object.
        :param host: MQTT broker hostname/IP.
        :param port: MQTT broker port (default: 1883).
        :param reply_topic: If a ``reply_topic`` is specified, then the action will wait for a response on this topic.
        :param timeout: If ``reply_topic`` is set, use this parameter to specify the maximum amount of time to
            wait for a response (default: 60 seconds).
        :param tls_cafile: If TLS/SSL is enabled on the MQTT server and the certificate requires a certificate authority
            to authenticate it, `ssl_cafile` will point to the provided ca.crt file (default: None).
        :param tls_certfile: If TLS/SSL is enabled on the MQTT server and a client certificate it required, specify it
            here (default: None).
        :param tls_keyfile: If TLS/SSL is enabled on the MQTT server and a client certificate key it required, specify
            it here (default: None).
        :param tls_version: If TLS/SSL is enabled on the MQTT server and it requires a certain TLS version, specify it
            here (default: None).
        :param tls_ciphers: If TLS/SSL is enabled on the MQTT server and an explicit list of supported ciphers is
            required, specify it here (default: None).
        :param username: Specify it if the MQTT server requires authentication (default: None).
        :param password: Specify it if the MQTT server requires authentication (default: None).
        """
        from paho.mqtt.client import Client

        if not host and not self.host:
            raise RuntimeError('No host specified and no default host configured')

        if not host:
            tls_cafile = self.tls_cafile
            tls_certfile = self.tls_certfile
            tls_keyfile = self.tls_keyfile
            tls_version = self.tls_version
            tls_ciphers = self.tls_ciphers
            username = self.username
            password = self.password

        client = Client()

        if username and password:
            client.username_pw_set(username, password)
        if tls_cafile:
            client.tls_set(ca_certs=tls_cafile, certfile=tls_certfile, keyfile=tls_keyfile, tls_version=tls_version,
                           ciphers=tls_ciphers)

        # Try to parse it as a platypush message or dump it to JSON from a dict/list
        if isinstance(msg, dict) or isinstance(msg, list):
            msg = json.dumps(msg)

            # noinspection PyBroadException
            try:
                msg = Message.build(json.loads(msg))
            except:
                pass

        client.connect(host, port, keepalive=timeout)
        response_buffer = io.BytesIO()

        try:
            response_received = threading.Event()

            if reply_topic:
                client.on_message = self._response_callback(reply_topic=reply_topic,
                                                            event=response_received,
                                                            buffer=response_buffer)
                client.subscribe(reply_topic)

            client.publish(topic, str(msg))
            if not reply_topic:
                return

            client.loop_start()
            ok = response_received.wait(timeout=timeout)
            if not ok:
                raise TimeoutError('Response timed out')
            return response_buffer.getvalue()
        finally:
            response_buffer.close()

            # noinspection PyBroadException
            try:
                client.loop_stop()
            except:
                pass

            client.disconnect()

    @staticmethod
    def _response_callback(reply_topic: str, event: threading.Event, buffer: IO[bytes]):
        def on_message(client, _, msg):
            if msg.topic != reply_topic:
                return

            buffer.write(msg.payload)
            client.loop_stop()
            event.set()
        return on_message

    @action
    def send_message(self, *args, **kwargs):
        """
        Alias for :meth:`platypush.plugins.mqtt.MqttPlugin.publish`.
        """
        return self.publish(*args, **kwargs)


# vim:sw=4:ts=4:et:
