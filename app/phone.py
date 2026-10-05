"""Phone numbers are stored in exactly one format: +234XXXXXXXXXX.

The BRD's loyalty incident (TE-5) happened because the same person was
saved as "0803 123 4567", "+234 803 123 4567" and "08031234567", and the
computer counted three customers. Normalising on the way in makes the
phone number a reliable key for spotting a returning customer.
"""
import re


class InvalidPhone(ValueError):
    pass


def normalise_ng_phone(raw: str) -> str:
    """Return a Nigerian mobile number as +234XXXXXXXXXX or raise InvalidPhone.

    Accepts the common ways people type it:
      08031234567, 0803 123 4567, 0803-123-4567,
      +2348031234567, +234 803 123 4567, 2348031234567, 8031234567
    """
    if raw is None:
        raise InvalidPhone("No phone number given")
    digits = re.sub(r"\D", "", raw)

    if len(digits) == 11 and digits.startswith("0"):
        national = digits[1:]
    elif len(digits) == 13 and digits.startswith("234"):
        national = digits[3:]
    elif len(digits) == 14 and digits.startswith("2340"):      # +234 0803... (a common slip)
        national = digits[4:]
    elif len(digits) == 10:
        national = digits
    else:
        raise InvalidPhone(f"'{raw}' isn't a Nigerian mobile number (expected e.g. 0803 123 4567)")

    if national[0] not in "789":
        raise InvalidPhone(f"'{raw}' isn't a Nigerian mobile number (it should start 07, 08 or 09)")
    return "+234" + national
