#  Copyright (c) Kuba Szczodrzyński 2023-5-14.

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from struct import unpack, unpack_from
from uuid import UUID

from Crypto.Cipher import AES
from datastruct import DataStruct
from datastruct.fields import field, virtual


@dataclass
class LsaKeyRevision(DataStruct):
    # adapted from:
    # https://github.com/tijldeneut/DPAPIck3/blob/main/dpapick3/registry.py
    minor: int = field("H")
    major: int = field("H")
    value: float = virtual(lambda ctx: float(f"{ctx.major}.{ctx.minor:02d}"))
    is_nt6: bool = virtual(lambda ctx: ctx.value > 1.09)


@dataclass
class LsaKey:
    revision: LsaKeyRevision
    sys_key: bytes
    enc_key: bytes
    key: bytes = None
    keys: dict[UUID, bytes] = None

    def __post_init__(self):
        self.decrypt()

    def decrypt(self):
        # https://github.com/tijldeneut/DPAPIck3/blob/main/dpapick3/crypto.py
        if self.revision.is_nt6:
            return self.decrypt_nt6()
        else:
            raise NotImplementedError()

    def decrypt_nt6(self):
        aes_key = sha256(self.sys_key)
        for _ in range(1000):
            aes_key.update(self.enc_key[28:60])
        keys = AES.new(aes_key.digest(), AES.MODE_ECB).decrypt(self.enc_key[60:])
        size = unpack_from("<L", keys)[0]
        keys = keys[16 : 16 + size]
        current_key = UUID(bytes_le=keys[4:20])
        num_rounds = unpack("<L", keys[24:28])[0]
        offs = 28
        self.keys = {}
        for _ in range(num_rounds):
            key_guid = UUID(bytes_le=keys[offs : offs + 16])
            key_type, key_len = unpack_from("<2L", keys[offs + 16 :])
            key = keys[offs + 24 : offs + 24 + key_len]
            self.keys[key_guid] = key
            offs += 24 + key_len
        self.key = self.keys[current_key]
        return current_key, self.keys


@dataclass
class LsaSecret(DataStruct):
    version: int = field("I")
    machine_cred: bytes = field(20)
    user_cred: bytes = field(20)
    upd_datetime: datetime = virtual(None)

    @staticmethod
    def build(lsa: LsaKey, secret: bytes, upd_time: bytes) -> "LsaSecret":
        if upd_time:
            upd_ts = int(unpack("<Q", upd_time)[0] / 10000000) - 11644473600
            upd_datetime = datetime.fromtimestamp(upd_ts)
        else:
            upd_datetime = None

        if lsa.revision.is_nt6:
            key_id = UUID(bytes_le=secret[4:20])
            if key_id in lsa.keys:
                aes_key = sha256(lsa.keys[key_id])
                for _ in range(1000):
                    aes_key.update(secret[28:60])
                decrypted = AES.new(aes_key.digest(), AES.MODE_ECB).decrypt(secret[60:])
                size = unpack_from("<L", decrypted)[0]
                value = decrypted[16 : 16 + size]
            else:
                value = None
        else:
            raise NotImplementedError()

        obj = LsaSecret.unpack(value)
        obj.upd_datetime = upd_datetime
        return obj
