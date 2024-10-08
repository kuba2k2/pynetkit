import hmac
from struct import pack


def pbkdf2(passphrase, salt, keylen, iterations, digest="sha1"):
    """
    Implementation of PBKDF2 that allows specifying digest algorithm.
    Returns the corresponding expanded key which is keylen long.
    """
    # https://github.com/tijldeneut/DPAPIck3/blob/main/dpapick3/crypto.py
    buff = b""
    i = 1
    while len(buff) < keylen:
        U = salt + pack("!L", i)
        i += 1
        derived = hmac.new(passphrase, U, digestmod=digest).digest()
        for r in range(iterations - 1):
            actual = hmac.new(passphrase, derived, digestmod=digest).digest()
            derived = (
                "".join(
                    [
                        chr(int(x, 16) ^ int(y, 16))
                        for (x, y) in zip(derived.hex(), actual.hex())
                    ]
                )
                .encode()
                .hex()
            )
            result = ""
            for j in range(len(derived)):
                if j % 2 == 1:
                    result += derived[j]
            derived = bytes.fromhex(result)
        buff += derived
    return buff[:keylen]
