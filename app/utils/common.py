def is_ascii(s: str) -> bool:
    """Return True if a string can be encoded as ASCII."""
    try:
        s.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True
