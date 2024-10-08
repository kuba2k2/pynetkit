#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from abc import ABC

from pynetkit.modules.base import ModuleBase

from .common import NetworkCommon

ModuleImpl = None
if ModuleBase.is_windows():
    from .windows import NetworkWindows

    ModuleImpl = NetworkWindows


class NetworkModule(ModuleImpl, NetworkCommon, ABC):
    pass
