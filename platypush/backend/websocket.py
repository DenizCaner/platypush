import asyncio
import os
import ssl
import threading
import websockets

from platypush.backend import Backend
from platypush.context import get_plugin, get_or_create_event_loop
from platypush.message import Message
from platypush.message.request import Request


class WebsocketBackend(Backend):
    """
    Backend to communicate messages over a websocket medium.

    Requires:

        * **websockets** (``pip install websockets``)
    """

    # Websocket client message recv timeout in seconds
    _websocket_client_timeout = 60

    def __init__(self, port=8765, bind_address='0.0.0.0', ssl_cert=None,
                 ssl_key=None, client_timeout=_websocket_client_timeout, **kwargs):
        """
        :param port: Listen port for the websocket server (default: 8765)
        :type port: int

        :param bind_address: Bind address for the websocket server (default: 0.0.0.0, listen for any IP connection)
        :type websocket_port: str

        :param ssl_cert: Path to the certificate file if you want to enable SSL (default: None)
        :type ssl_cert: str

        :param ssl_key: Path to the key file if you want to enable SSL (default: None)
        :type ssl_key: str

        :param client_timeout: Timeout without any messages being received before closing a client connection. A zero timeout keeps the websocket open until an error occurs (default: 60 seconds)
        :type ping_timeout: int
        """

        super().__init__(**kwargs)

        self.port = port
        self.bind_address = bind_address
        self.ssl_context = None
        self.client_timeout = client_timeout

        if ssl_cert:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ssl_context.load_cert_chain(
                certfile=os.path.abspath(os.path.expanduser(ssl_cert)),
                keyfile=os.path.abspath(os.path.expanduser(ssl_key)) if ssl_key else None
            )

    def send_message(self, msg):
        websocket = get_plugin('websocket')
        websocket_args = {}

        if self.ssl_context:
            url = 'wss://localhost:{}'.format(self.port)
            websocket_args['ssl'] = self.ssl_context
        else:
            url = 'ws://localhost:{}'.format(self.port)

        websocket.send(url=url, msg=msg, **websocket_args)


    def run(self):
        super().run()

        async def serve_client(websocket, path):
            self.logger.debug('New websocket connection from {}'.
                             format(websocket.remote_address[0]))

            try:
                while True:
                    if self.client_timeout:
                        msg = await asyncio.wait_for(websocket.recv(),
                                                     timeout=self.client_timeout)
                    else:
                        msg = await websocket.recv()

                    msg = Message.build(msg)
                    self.logger.info('Received message from {}: {}'.
                                    format(websocket.remote_address[0], msg))

                    self.on_message(msg)

                    if isinstance(msg, Request):
                        response = self.get_message_response(msg)
                        if not response:
                            return

                        self.logger.info('Processing response on the websocket backend: {}'.
                                            format(response))

                        await websocket.send(str(response))

            except Exception as e:
                if isinstance(e, websockets.exceptions.ConnectionClosed):
                    self.logger.debug('Websocket client {} closed connection'.
                                    format(websocket.remote_address[0]))
                elif isinstance(e, asyncio.TimeoutError):
                    self.logger.debug('Websocket connection to {} timed out'.
                                    format(websocket.remote_address[0]))
                else:
                    self.logger.exception(e)

        self.logger.info('Initialized websocket backend on port {}, bind address: {}'.
                         format(self.port, self.bind_address))

        websocket_args = {}
        if self.ssl_context:
            websocket_args['ssl'] = self.ssl_context

        loop = get_or_create_event_loop()
        server = websockets.serve(serve_client, self.bind_address, self.port,
                                  **websocket_args)

        loop.run_until_complete(server)
        loop.run_forever()


# vim:sw=4:ts=4:et:
