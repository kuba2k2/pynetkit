#  Copyright (c) Kuba Szczodrzyński 2023-5-14.

from dataclasses import dataclass
from datetime import datetime
from enum import IntFlag
from hashlib import sha1
from hmac import HMAC
from uuid import UUID

from Crypto.Cipher import AES
from datastruct import DataStruct, datastruct
from datastruct.adapters.misc import utf16le_field, uuid_le_field
from datastruct.adapters.time import filetime_field
from datastruct.fields import built, const, eval_into, field, padding, subfield, virtual

from .pbkdf2 import pbkdf2
from .types import IV_LEN, KEY_LEN, DpapiAlgoCrypt, DpapiAlgoHash


class DpapiKeyPolicy(IntFlag):
    USE_SHA1 = 0b1000
    BACKUP = 0b0100


@dataclass
class DpapiKey(DataStruct):
    version: int = const(2, "key slot version")(field("I"))
    salt: bytes = field(16)
    pbkdf2_iter_count: int = field("I")
    alg_hash: DpapiAlgoHash = field("I")
    alg_crypt: DpapiAlgoCrypt = field("I")
    key_data: bytes = field(lambda ctx: ctx.key_len or ctx._.key_len)
    key: bytes = virtual(None)
    key_hash: bytes = virtual(None)
    hmac_salt: bytes = virtual(None)
    hmac_hash: bytes = virtual(None)

    def decrypt(self, cred: bytes):
        master_secret = pbkdf2(
            cred,
            self.salt,
            KEY_LEN[self.alg_crypt] + IV_LEN[self.alg_crypt],
            self.pbkdf2_iter_count,
            "sha512",
        )
        key = master_secret[0:32]
        iv = master_secret[32:48]
        decrypted = AES.new(key, AES.MODE_CBC, iv).decrypt(self.key_data)
        self.key = decrypted[-64:]
        self.key_hash = sha1(self.key).digest()
        self.hmac_salt = decrypted[0:16]
        self.hmac_hash = decrypted[16 : 16 + KEY_LEN[self.alg_hash]]

        hmac1 = HMAC(
            key=cred, msg=self.hmac_salt, digestmod=self.alg_hash.name
        ).digest()
        hmac2 = HMAC(key=hmac1, msg=self.key, digestmod=self.alg_hash.name).digest()
        assert hmac2 == self.hmac_hash

        return self.key


@dataclass
@datastruct(padding_pattern=b"\x00")
class DpapiMasterKeyFile(DataStruct):
    version: int = field("I", default=2)
    _1: ... = padding(8)
    guid: str = utf16le_field(72)
    _2: ... = padding(8)
    policy: DpapiKeyPolicy = field("I")
    master_key_len: int = built("I", lambda ctx: len(ctx.master_key.key) + 32)
    _3: ... = padding(4)
    backup_key_len: int = built("I", lambda ctx: len(ctx.backup_key.key) + 32)
    _4: ... = padding(4)
    cred_hist_len: int = field("I", default=20)
    _5: ... = padding(4)
    _6: ... = padding(8)
    _7: ... = eval_into("key_len", lambda ctx: ctx.master_key_len - 32)
    master_key: DpapiKey = subfield()
    _8: ... = eval_into("key_len", lambda ctx: ctx.backup_key_len - 32)
    backup_key: DpapiKey = subfield()
    cred_hist_version: int = field("I")
    cred_hist_guid: UUID = uuid_le_field()


@dataclass
class DpapiPreferredKeyFile(DataStruct):
    master_key_guid: UUID = uuid_le_field()
    expiration_time: datetime = filetime_field()
