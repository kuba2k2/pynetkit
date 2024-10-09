#  Copyright (c) Kuba Szczodrzyński 2023-5-14.

from enum import IntEnum
from uuid import UUID


class DpapiAlgoCrypt(IntEnum):
    AES256 = 0x6610
    _3DES = 1
    RC4 = 2


class DpapiAlgoHash(IntEnum):
    SHA512 = 0x800E
    SHA1 = 0


WCP_GUID = UUID("df9d8cd0-1501-11d1-8c7a-00c04fc297eb")
KEY_LEN = {
    DpapiAlgoCrypt.AES256: 256 // 8,
    DpapiAlgoHash.SHA512: 512 // 8,
}
IV_LEN = {
    DpapiAlgoCrypt.AES256: 256 // 16,
    DpapiAlgoHash.SHA512: 512 // 16,
}
