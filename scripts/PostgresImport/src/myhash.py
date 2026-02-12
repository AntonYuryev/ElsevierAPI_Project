import hashlib


def myhash(text):
    """replaces the built in python hash function with one that is deterministic"""

    if isinstance(text, str):
        text = text.encode("utf8")

    # use md5 to create a hash
    digest = hashlib.md5(text).hexdigest()
    dint = int(digest, 16)  # create 128 bit integer

    # xor high and low halves
    result = ((dint >> 64) ^ dint) & 0xFFFFFFFFFFFFFFFF
    # if greater than max 64bit signed int, make negative. python doesn't wrap on overflow
    # because it never overflows
    if result > 0x7FFFFFFFFFFFFFFF:
        result = -(result & 0x7FFFFFFFFFFFFFFF)

    return result
