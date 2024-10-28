#  Copyright (c) Kuba Szczodrzyński 2023-9-9.

from logging import info
from uuid import UUID
from winreg import HKEY_LOCAL_MACHINE as HKLM
from winreg import OpenKey, QueryValueEx

from win32api import RegQueryInfoKeyW

from .key import DpapiKey, DpapiMasterKeyFile, DpapiPreferredKeyFile
from .lsa import LsaKey, LsaKeyRevision, LsaSecret
from .store import DpapiKeyStore


class Dpapi:
    lsa: LsaKey = None
    secret: LsaSecret = None
    key_cache: dict[UUID, tuple[bytes, bytes]] = None

    def load_credentials(self) -> None:
        with OpenKey(HKLM, "SYSTEM\\Select") as key:
            control_set, _ = QueryValueEx(key, "Current")

        with OpenKey(HKLM, f"SYSTEM\\ControlSet{control_set:03d}\\Control\\Lsa") as key:
            keys = ["JD", "Skew1", "GBG", "Data"]
            key_data = ""
            for subkey in keys:
                with OpenKey(key, subkey) as sk:
                    key_data += RegQueryInfoKeyW(sk)["Class"]
            key_data = bytes.fromhex(key_data)
            transforms = [8, 5, 4, 2, 11, 9, 13, 3, 0, 6, 1, 12, 14, 10, 15, 7]
            sys_key = ""
            for i in range(len(key_data)):
                sys_key += f"{key_data[transforms[i]]:02x}"
            sys_key = bytes.fromhex(sys_key)

        with OpenKey(HKLM, "SECURITY\\Policy\\PolRevision") as key:
            val, _ = QueryValueEx(key, "")
            lsa_key_revision = LsaKeyRevision.unpack(val)

        if lsa_key_revision.is_nt6:
            enc_key_name = "PolEKList"
        else:
            enc_key_name = "PolSecretEncryptionKey"

        with OpenKey(HKLM, f"SECURITY\\Policy\\{enc_key_name}") as key:
            enc_key, _ = QueryValueEx(key, "")

        self.lsa = LsaKey(
            revision=lsa_key_revision,
            sys_key=sys_key,
            enc_key=enc_key,
        )

        with OpenKey(HKLM, "SECURITY\\Policy\\Secrets\\DPAPI_SYSTEM") as key:
            with OpenKey(key, "CurrVal") as cv:
                secret, _ = QueryValueEx(cv, "")
            with OpenKey(key, "CupdTime") as ct:
                upd_time, _ = QueryValueEx(ct, "")

        self.secret = LsaSecret.build(
            lsa=self.lsa,
            secret=secret,
            upd_time=upd_time,
        )
        self.key_cache = {}

    @staticmethod
    def list_keys(store: DpapiKeyStore) -> list[UUID]:
        return [
            UUID(p.name)
            for p in store.path.glob("*")
            if p.name.count("-") == 4 and len(p.name) == 36
        ]

    @staticmethod
    def get_preferred_key(store: DpapiKeyStore) -> UUID:
        preferred_path = store.path.joinpath("Preferred")
        if not preferred_path.is_file():
            raise FileNotFoundError("Preferred key does not exist")
        with preferred_path.open("rb") as f:
            preferred_key = DpapiPreferredKeyFile.unpack(f)
        return preferred_key.master_key_guid

    def get_key_builder(self, store: DpapiKeyStore):
        def key_builder(guid: UUID) -> DpapiKey:
            if self.key_cache is None:
                raise Exception("Machine credentials not loaded yet")
            if guid in self.key_cache:
                key_bytes, key_hash = self.key_cache[guid]
                key = DpapiKey.unpack(key_bytes, key_len=len(key_bytes) - 32)
                key.key_hash = key_hash
                return key

            key_path = store.path.joinpath(str(guid))
            if not key_path.is_file():
                raise FileNotFoundError(
                    f"Key {guid} not found in store {store.scope}(user={store.user})"
                )
            with key_path.open("rb") as f:
                master_key_file = DpapiMasterKeyFile.unpack(f)

            info("Decrypting DPAPI master key, this will take a moment")
            master_key = master_key_file.master_key
            master_key.decrypt(
                self.secret.user_cred if store.user else self.secret.machine_cred
            )

            key_bytes = master_key.pack(key_len=len(master_key.key_data))
            self.key_cache[guid] = key_bytes, master_key.key_hash
            return master_key

        return key_builder
