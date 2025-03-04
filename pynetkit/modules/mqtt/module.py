#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

import asyncio
import logging
from asyncio import AbstractEventLoop, Future
from functools import partial
from ipaddress import IPv4Address
from logging import DEBUG, LogRecord
from threading import Thread

from amqtt.broker import Broker
from amqtt.client import MQTTClient
from amqtt.mqtt.constants import QOS_0
from amqtt.mqtt.protocol.broker_handler import BrokerProtocolHandler
from amqtt.session import ApplicationMessage

from pynetkit.modules.base import ModuleBase

from .events import (
    MqttClientConnectedEvent,
    MqttClientDisconnectedEvent,
    MqttClientSubscriptionAddEvent,
    MqttClientSubscriptionDelEvent,
    MqttMessageEvent,
)
from .types import MessageHandler


class MqttModule(ModuleBase):
    # pre-run configuration
    _address: IPv4Address = None
    _mqtt_port: int = None
    # runtime configuration
    handlers: list[tuple[str, MessageHandler]] = None
    # server handle
    _broker_thread: Thread | None = None
    _broker_loop: AbstractEventLoop | None = None
    _broker: Broker | None = None
    _broker_clients: dict[str, IPv4Address] | None = None
    _client: MQTTClient | None = None

    def __init__(self):
        super().__init__()
        self.handlers = []

    def configure(
        self,
        address: IPv4Address,
        mqtt: int = 1883,
    ) -> None:
        if self._broker is not None or self._client is not None:
            raise RuntimeError("Server already running, stop to reconfigure")
        self._address = address
        self._mqtt_port = mqtt

    async def start(self) -> None:
        if not self._address:
            raise RuntimeError("Server not configured")

        logging.getLogger("passlib.utils")
        logging.getLogger("amqtt.adapters")
        logging.getLogger("amqtt.mqtt.protocol.handler")
        logging.getLogger("amqtt.broker.plugins.auth_anonymous")
        for name in logging.Logger.manager.loggerDict.keys():
            if name.partition(".")[0] not in ["amqtt", "passlib", "transitions"]:
                continue
            logger = logging.getLogger(name)
            logger.level = logging.WARNING

        broker_future = self.make_future()
        self._broker_thread = Thread(
            target=self.broker_entrypoint,
            args=[broker_future],
            daemon=True,
        )
        self._broker_thread.start()
        await broker_future

        await super().start()

    def broker_entrypoint(self, future: Future) -> None:
        self.resolve_future(future)
        if not self._mqtt_port:
            return
        self.info(f"Starting MQTT broker on {self._address}:{self._mqtt_port}")
        self._broker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._broker_loop)

        config = {
            "listeners": {
                "default": {
                    "type": "tcp",
                    "bind": f"{self._address}:{self._mqtt_port}",
                },
            },
            "sys_interval": 10,
            "auth": {
                "allow-anonymous": True,
                "plugins": ["auth_anonymous"],
            },
            "topic-check": {
                "enabled": False,
            },
        }

        self._broker_clients = {}
        self._broker = Broker(config)
        self._broker.logger.handle = self.broker_logger_handle
        self._broker.logger.setLevel(DEBUG)
        self._broker_loop.run_until_complete(self._broker.start())
        self._broker_loop.run_forever()

    async def run(self) -> None:
        if not self._mqtt_port:
            return
        self.info(f"Connecting to MQTT broker on {self._address}:{self._mqtt_port}")
        self._client = MQTTClient()
        await self._client.connect(f"mqtt://{self._address}:{self._mqtt_port}/")
        self.debug("MQTT connected")

        topics = set(topic for topic, _ in self.handlers)
        self.info(f"Subscribing to {', '.join(topics)}")
        await self._client.subscribe([(topic, QOS_0) for topic in topics])

        while self.should_run and self._client is not None:
            message: ApplicationMessage = await self._client.deliver_message()
            if not self._broker:
                # TODO adjust for external broker
                break
            for topic, func in self.handlers:
                if not self._broker.matches(message.topic, topic):
                    continue
                MqttMessageEvent(message).broadcast()
                try:
                    await func(message.topic, bytes(message.data))
                except Exception as e:
                    self.exception("Message handler raised exception", exc_info=e)

    async def stop(self) -> None:
        self.should_run = False
        await super().stop()
        if self._broker:
            self._broker_loop.stop()
            self._broker_thread.join()

    async def add_handler(
        self,
        func: MessageHandler,
        topic: str,
    ) -> None:
        if not self._client:
            self.handlers.append((topic, func))
            return
        if any(t == topic for t, _ in self.handlers):
            return
        self.handlers.append((topic, func))
        self.info(f"Subscribing to {topic}")
        await self._client.subscribe([(topic, QOS_0)])

    async def add_handlers(self, obj: object) -> None:
        for cls in type(obj).__bases__ + (type(obj),):
            for func in cls.__dict__.values():
                if not hasattr(func, "__topics__"):
                    continue
                # decorated function is not bound to instance
                bound_func = partial(func, obj)
                for topic in getattr(func, "__topics__"):
                    await self.add_handler(bound_func, topic)

    def clear_handlers(self) -> None:
        self.handlers = []

    async def publish(self, topic: str, message: bytes) -> None:
        if not self._client:
            return
        await self._client.publish(topic, message)

    def broker_client_to_address(self, client_id: str) -> IPv4Address:
        # noinspection PyProtectedMember
        session, handler = self._broker._sessions[client_id]
        handler: BrokerProtocolHandler
        remote_address, remote_port = handler.writer.get_peer_info()
        return IPv4Address(remote_address)

    def broker_logger_handle(self, record: LogRecord) -> None:
        msg = record.msg
        if "Start messages handling" in msg:
            client_id = msg.partition(" ")[0]
            address = self.broker_client_to_address(client_id)
            MqttClientConnectedEvent(client_id, address).broadcast()
        elif "Disconnecting session" in msg:
            client_id = msg.partition(" ")[0]
            address = self.broker_client_to_address(client_id)
            MqttClientDisconnectedEvent(client_id, address).broadcast()
        elif "Begin broadcasting messages retained due to subscription" in msg:
            topic = msg.partition("'")[2].partition("'")[0]
            client_id = msg.partition("(client id=")[2][0:-1]
            address = self.broker_client_to_address(client_id)
            MqttClientSubscriptionAddEvent(client_id, address, topic).broadcast()
        elif "Removing subscription on topic" in msg:
            topic = msg.partition("'")[2].partition("'")[0]
            client_id = msg.partition("(client id=")[2][0:-1]
            address = self.broker_client_to_address(client_id)
            MqttClientSubscriptionDelEvent(client_id, address, topic).broadcast()
