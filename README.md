# pynetkit

Reverse engineering utilities for several popular network protocols.

## Introduction

pynetkit allows running custom servers, that listen and answer to several network protocols. The servers can be
configured programmatically, which lets you easily add network handlers, change their configuration, etc. Additionally,
the servers receive and broadcast events about what's happening, so that you can respond to the current state.

The unconventional style of the network servers is particularly useful for reverse engineering embedded/IoT devices
and finding various kinds of vulnerabilities.

## Installation

pynetkit can be installed from PyPI:

```
pip install pynetkit
```

or from sources, using Poetry.

After installation, a `pynetkit` command will be available to access the built-in CLI.

## Implemented modules

Below are the modules currently implemented in the project.

- `base` - Common utilities and base classes for all modules.
- `dhcp` - DHCP server that can give out dynamic or static leases from a specific IP address range.
- `dns` - DNS server that can answer queries based on a set of RegEx patterns, as well as forward queries to an upstream server.
- `http` - HTTP/HTTPS server that can call request handlers based on various parameters of the request. SSL is supported by using certificates or PSK authentication.
- `mqtt` - MQTT broker that will also listen to incoming messages and call message handlers based on their parameters.
- `network` - Network interface configuration module, that can list network interfaces, read and change their IP configuration and ping hosts.
- `ntp` - NTP server that can answer time queries, optionally changing the returned time by a dynamically chosen amount.
- `proxy` - TCP/TLS/HTTP proxy that can redirect traffic to a different IP address/port based on the requested host name (TLS SNI or HTTP Host header).
- `wifi` - Wi-Fi configuration module, that can scan for Wi-Fi networks, connect to a network and create an access point (SoftAP).

The `network` and `wifi` modules are currently Windows-only - the Linux implementation is not written yet.

## Command line interface

Since v1.0.0, a built-in CLI is available. By default, a curses-based interactive TUI is started (unless it's not
available on your terminal, or the `-s` flag is given). You can configure it using the following options:

```shell
λ pynetkit --help
Usage: pynetkit [OPTIONS]

  Reverse engineering utilities for several popular network protocols

Options:
  -v, --verbose        Output debugging messages (repeat to output more)
  -T, --traceback      Print complete exception traceback
  -t, --timed          Prepend log lines with timing info
  -r, --raw-log        Output logging messages with no additional styling
  -s, --simple         Use the simple CLI (instead of curses-based TUI)
  -P, --pycharm-debug  Connect to a PyCharm/IntelliJ debugger on
                       127.0.0.1:1234
  -h, --help           Show this message and exit.
```

### Using the interactive CLI

pynetkit is configured using **commands**. At any point, pressing `Tab` shows available command completions, and
pressing `?` (or typing `help`) shows a detailed help screen for the particular command.

Each of the **modules** (listed above) has its own CLI. When configured using commands, modules can preserve their
settings in **config files**.

There is a dedicated **`config` command**, that allows you to save the entire configuration of pynetkit to a YAML file.
Everything that you configured for a particular module will be saved, **including its started/stopped state**.

The config file system allows you to easily **save working settings and easily restore them later**.

#### Using multi-instance modules

Certain modules, such as `dhcp`, `dns` or `proxy` allow you to create multiple instances (i.e. multiple servers).

- To create a new instance, use `<module> create [total]`. The parameter specifies a total number of instances that should be available. If omitted, one new instance is added.
- To access/configure a particular instance, use `<module> -@ <index> <command...>`, for example `dhcp -@ 2 start` to start the 2nd DHCP server.
- To remove a particular instance, use `<module> -@ <index> destroy`. Note that the remaining modules will be re-indexed.
- Once you have more than one instance, you must use the `-@ <index>` specifier for each of the module's commands.

---

### Command reference

This is a list of the most useful commands from each module. Not everything is described; all commands are always
documented in the help screens.

#### `config`

- (no parameters) - Show available subcommands, a list of all loaded modules, as well as whether the current config state was saved to a file.
- `meta` - Each config file can have optional metadata information, such as the name, version or author of the config.
- `reset [module]` - Reset a particular module (or all modules) to the default values, i.e. remove all configuration options.
- `save <path>` - Save all modules' configuration to a YAML file. File path is only required on first save.
- `load <path>` - Load all modules' configuration from a YAML file (will first unload the previous configuration).
- `dump [module]` - Show the current configuration as YAML. Can also show individual modules only.
- `commands [module]` - Show commands that should be executed to recreate the current configuration state.

The sections below describe commands associated with particular pynetkit modules.

---

#### `network`

This is probably one of the most complicated modules... but believe me, I couldn't find any better way to do it.

The network module is responsible for adapter assignment, as well as IP address configuration.

- (no parameters) - List the **configured** network adapters, as well as their **configured** IP addresses.
- `list` - List **all** available network adapters, as well as their **actual** IP addresses and whether they are configured.
- `use <index> <query>` - Assign a network adapter to a chosen **index** (this is what makes it **configured**).
- `addr <index> ...` - Configure IP addresses of the given network interface.
  - `add <address/CIDR>` - Add a new address to the adapter.
  - `del <address/CIDR>` - Remove an address from the adapter.
  - `set <address/CIDR>` - Set an address to the adapter (remove all existing addresses).
  - `dhcp` - Enable DHCP (and remove all existing addresses).
  - `flush` - Just remove all existing addresses.
  - `restore` - Reapply the **configured** address(es) to the adapter.

The idea behind **configuration** is that a particular network adapter is assigned to a numeric **index**. This makes
it possible to share the configuration files, i.e. make them OS- and hardware-independent.

The **query** passed to `network use ...` can either be the name of an adapter (`Ethernet`, `eth0`, etc.) or its type -
that's the preferred way, since adapter names differ between hosts. The command `network use 1 wired` will assign a
wired ethernet adapter to index 1 - on every platform.

The `network use ...` command also accepts an extra `-k`/`--keep` flag. This tells pynetkit to preserve the query in the
configuration file. Without this flag, the program will use default assignments at every startup, that is:

- Index 1: Wired
- Index 2: Wireless Station
- Index 3: Wireless Access Point

I would recommend **using the default mappings**, since they already account for most use cases.

Note that IP addresses assigned using `network addr ...` are always stored in the configuration, regardless of the
`--keep` flag.

---

#### `wifi`

The Wi-Fi module is responsible for connecting wireless adapters to networks, as well as creating an access point.

- (no parameters) - List the configured Wi-Fi adapters, as well as their **configured** SSID/password.
- `show` - Show the **actual** connection states of all configured Wi-Fi adapters.
- `scan` - Scan for available networks.
- `connect <ssid> [password]` - Connect to a wireless network. Secured networks need a password for connection.
- `disconnect` - Disconnect from the current network, if any.
- `ap <ssid> [password]` - Start a wireless access point (AP). Supplying a password will make the network secured.
- `apstop` - Stop the access point, if it's running.

The Wi-Fi adapters are configured using the `network` module (i.e. the same indexes apply here).

If there are multiple Wi-Fi cards installed, use `-@ <index>` after the subcommand name to reference a particular
adapter.

Note that Linux doesn't (by default) have separate Wi-Fi adapters for STA and AP modes, unlike Windows. If you need
to use both modes simultaneously, you will need to create a new virtual interface using `iwconfig` or similar.
Also note that not every Wi-Fi card supports running both AP and STA at the same time.

---

#### `dhcp`

This module provides a configurable DHCP server.

All options except `listen` can be configured while the server is running.

- (no parameters) - Show DHCP server state, configuration and active DHCP client leases.
- `start`/`stop` - Allows to start or stop the DHCP server.
- `listen <address> [port]` - Allows to change the listen address (default: `0.0.0.0:67`).
- `interface <address/CIDR>` - Required: set the DHCP server's network interface address (the one visible to clients).
- `range <first> <last>` - Set a range of IP addresses given out to clients (default: use entire subnet).

---

#### `dns`

This module provides a DNS server, that supports regular expressions and upstream query forwarding.

All options except `listen` can be configured while the server is running.

- (no parameters) - Show DNS server state and created DNS records.
- `start`/`stop` - Allows to start or stop the DNS server.
- `listen <address> [port]` - Allows to change the listen address (default: `0.0.0.0:53`).
- `set <name> <type> <answer...>` - Create a new (locally-resolved) DNS record.
- `upstream <address> [name] [type]` - Forward matching queries to an upstream DNS server (or all, if not specified).
- `move <from> <to>` - Move a record between the given indexes.

As you can see, the DNS records **resolving order matters**. That is because `name` and `type` parameters **use RegEx**.
For example, `.*` will match all names/types, and `TXT|SRV` will match only specified record types.

If you put an `.*` record **before** more specific records, they will NOT be resolved, because the wildcard record will
take precedence.

---

#### `ntp`

This module provides a simple NTP server.

All options except `listen` can be configured while the server is running.

- (no parameters) - Show NTP server state and configuration.
- `start`/`stop` - Allows to start or stop the NTP server.
- `listen <address> [port]` - Allows to change the listen address (default: `0.0.0.0:123`).
- `offset <address> <time>` - Offset the returned timestamp by a specific time delta (e.g. `5 days`, `10 hours`).

---

#### `proxy`

This module provides a TCP/TLS/HTTP server, which can proxy connections based on the requested hostname. 

All options except `listen` and `port` can be configured while the server is running.

- (no parameters) - Show the proxy server state and configured routes.
- `listen <address>` - Allows to change the listen address (default: `0.0.0.0`).
- `port <port> <protocol>` - Add a **listening port**, assign the specified protocol (`any`, `raw`, `tls`, `http`).
- `set <source> <target> [proxy]` - Create/modify a **proxy route** (see below).
- `move <from> <to>` - Move a **route** between indexes (the first matching route is used when proxying).
- `test <URL>` - Check what target URL would be used for the given request.

The proxy ports must be configured first - **the proxy will only listen on these ports**.

Then, a **route** must be created - routes are basically instructions for where to proxy the traffic.
- Source format is: `[scheme://]host[:port][/path]`, where `scheme`, `port` and `path` are optional (will match any).
- Target format is: `host[:port][/path]`, where `port` and `path` are optional (will match any).
- The `host` and `path` parts in `source` can be a RegEx. Capture groups in `target` can be referenced using `$1`, `$2`, etc.
- The `path` argument, if present, must begin with `/` (this alone will only match the "root" resource).
- The `path` argument also matches the query string (`?a=b&c=d`), use something like `host.com/my/file.html(.*)` if you want to match any query.
- Use `.*` or `""` for `source` to match any request.
- Use `.*` or `""` for `target` to use the same address as source.
- The optional `proxy` parameter specifies an external HTTP proxy address.

Perhaps a better way to understand the configuration will be to see what happens for each request:

1. If automatic protocol matching is enabled for this port (`proxy port <...> any`), try to detect the protocol type (TLS, HTTP or raw TCP otherwise).
2. Knowing the protocol type, try to detect the request hostname (HTTP `Host:` header, TLS handshake SNI). For raw TCP, the hostname is evaluated to `""`.
3. For HTTP protocol, try to extract the request path. For other protocols (TLS, TCP), the path is evaluated to `""`.
4. Knowing the request port, hostname, path and protocol type, **find the first matching route**.
5. **Forward traffic** to the target hostname/port/path, optionally via an external HTTP proxy.

By default, the proxy module is configured to forward traffic on ports 80 and 443 to the origin server.

**Remember:** the proxy does NOT modify requests! If you specify a different target host name, it will be contacted with
the **original** request - that is, the `Host:` header or TLS SNI values will NOT be modified. The only exception is
when using `path` for a HTTP source/target. This will only modify the request line.

## Using pynetkit programmatically

This was the first option of using pynetkit - by creating custom Python modules. It can still be used to extend the
abilities of the program, as well as to add new CLI commands.

**Note that you can skip this part, if all you need is the CLI.**

### A brief on modules

All pynetkit modules follow the same pattern - they have their own thread (or several threads) that can be started or
stopped using AsyncIO method calls. In order to receive events, the caller class should inherit from `ModuleBase`.

`ModuleBase` has an async `run()` method, which is executed on the module's thread. All threads created by `ModuleBase`
start their work in `entrypoint()`; it's not recommended to override this function. However, if unusual configuration
is needed *before* starting the thread (such as starting a few of them), the async `start()` method can be overridden.

### Example

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
