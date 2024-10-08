# pynetkit

Reverse engineering utilities for several popular network protocols.

## Introduction

pynetkit allows running custom servers, that listen and answer to several network protocols. The servers can be
configured programmatically, which lets you easily add network handlers, change their configuration, etc. Additionally,
the servers receive and broadcast events about what's happening, so that you can respond to the current state.

The unconventional style of the network servers is particularly useful for reverse engineering embedded/IoT devices
and finding various kinds of vulnerabilities.

## Implemented modules

Below are the modules currently implemented in the project.

- `base` - Common utilities and base classes for all modules.
- `dhcp` - DHCP server that can give out dynamic or static leases from a specific IP address range.
- `dns` - DNS server that can answer queries based on a set of RegEx patterns, as well as forward queries to an upstream server.
- `http` - HTTP/HTTPS server that can call request handlers based on various parameters of the request. SSL is supported by using certificates or PSK authentication.
- `mqtt` - MQTT broker that will also listen to incoming messages and call message handlers based on their parameters.
- `network` - Network interface configuration module, that can list network interfaces, read and change their IP configuration and ping hosts.
- `proxy` - TCP/TLS/HTTP proxy that can redirect traffic to a different IP address/port based on the requested host name (TLS SNI or HTTP Host header).
- `wifi` - Wi-Fi configuration module, that can scan for Wi-Fi networks, connect to a network and create an access point (SoftAP).

The `network` and `wifi` modules are currently Windows-only - the Linux implementation is not written yet.

## A brief on modules

All pynetkit modules follow the same pattern - they have their own thread (or several threads) that can be started or
stopped using AsyncIO method calls. In order to receive events, the caller class should inherit from `ModuleBase`.

`ModuleBase` has an async `run()` method, which is executed on the module's thread. All threads created by `ModuleBase`
start their work in `entrypoint()`; it's not recommended to override this function. However, if unusual configuration
is needed *before* starting the thread (such as starting a few of them), the async `start()` method can be overridden.

## Example

An example class that starts an HTTP server and redirect all DNS queries to it:

```python
import asyncio
import logging
from ipaddress import IPv4Address
from logging import DEBUG

import pynetkit.modules.http as httpm
from pynetkit.modules.base import BaseEvent, ModuleBase, subscribe
from pynetkit.modules.dns import DnsModule
from pynetkit.modules.http import HttpModule, Request, Response


class Example(ModuleBase):
    dns: DnsModule
    http: HttpModule

    def __init__(self):
        super().__init__()
        self.dns = DnsModule()
        self.http = HttpModule()

    async def run(self) -> None:
        self.register_subscribers()
        await self.event_loop_thread_start()

        self.dns.add_record(".*", "A", IPv4Address("0.0.0.0"))
        await self.dns.start()

        self.http.configure(
            address=IPv4Address("0.0.0.0"),
            http=80,
            https=0,
        )
        self.http.add_handlers(self)
        await self.http.start()

        while True:
            await asyncio.sleep(1.0)

    async def cleanup(self) -> None:
        await super().cleanup()
        await self.http.stop()
        await self.dns.stop()

    @subscribe(BaseEvent)
    async def on_event(self, event) -> None:
        self.info(f"EVENT: {event}")

    @httpm.get("/hello")
    async def on_hello(self, request: Request) -> Response:
        return {
            "Hello": "World",
            "Headers": request.headers,
        }

    @httpm.get("/.*")
    async def on_http(self, request: Request) -> Response:
        return {
            "Error": "Not Found",
            "Path": request.path,
        }


def main():
    logger = logging.getLogger()
    logger.level = DEBUG
    example = Example()
    example.entrypoint()


if __name__ == "__main__":
    main()

```

## License

```
MIT License

Copyright (c) 2024 Kuba Szczodrzyński

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```
