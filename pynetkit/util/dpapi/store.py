#  Copyright (c) Kuba Szczodrzyński 2023-9-10.

import os
import platform
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DpapiKeyScope(Enum):
    LOCAL_SYSTEM = "S-1-5-18"
    LOCAL_SERVICE = "S-1-5-19"
    NETWORK_SERVICE = "S-1-5-20"
    USER = None


@dataclass
class DpapiKeyStore:
    scope: DpapiKeyScope
    user: bool
    path: Path

    @staticmethod
    def get(scope: DpapiKeyScope, user: bool = False) -> "DpapiKeyStore":
        if scope.value:
            is_py64 = sys.maxsize > 2**32
            is_win64 = platform.machine().endswith("64")
            is_wow64 = is_win64 and not is_py64
            store_path = Path(
                os.environ["WINDIR"],
                "Sysnative" if is_wow64 else "System32",
                "Microsoft",
                "Protect",
                scope.value,
            )
            if user:
                store_path = store_path.joinpath("User")
        else:
            store_path = Path(os.environ["APPDATA"], "Microsoft", "Protect")
            store_path = next(store_path.glob("S-1-5-*"))
        return DpapiKeyStore(scope, user, store_path)
