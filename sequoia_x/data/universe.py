"""Common stock-universe rules."""

import unicodedata


def eligible(code: str, name: str, exchange: str) -> bool:
    prefixes = {
        "sh": ("600", "601", "603", "605", "688"),
        "sz": ("000", "001", "002", "003", "300", "301"),
    }
    name = "".join(unicodedata.normalize("NFKC", name).upper().split())
    return (
        len(code) == 6
        and code.isdigit()
        and bool(name)
        and code.startswith(prefixes.get(exchange, ()))
        and "ST" not in name
        and "退" not in name
    )
