#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from abc import ABC

from pynetkit.modules.base import ModuleBase

from .common import NetworkCommon

if ModuleBase.is_windows():
    from .windows import NetworkWindows as ModuleImpl
elif ModuleBase.is_linux():
    from .linux import NetworkLinux as ModuleImpl
else:
    raise NotImplementedError("Platform not supported")


class NetworkModule(ModuleImpl, NetworkCommon, ABC):
    pass
