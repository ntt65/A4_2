import re


def mask_resident_id(text: str) -> str:
    return re.sub(r"\b(\d{6})-?(\d)\d{6}\b", r"\1-\2******", text)


def mask_card_number(text: str) -> str:
    return re.sub(r"\b(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})\b", r"\1-****-****-\4", text)


def mask_phone_number(text: str) -> str:
    def repl(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) == 11:
            return f"{digits[:3]}-****-{digits[-4:]}"
        if len(digits) == 10 and digits.startswith("02"):
            return f"02-***-{digits[-4:]}"
        if len(digits) == 10:
            return f"{digits[:3]}-***-{digits[-4:]}"
        return match.group(0)

    return re.sub(r"\b(?:0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}\b", repl, text)


def mask_personal_info(text: str) -> str:
    masked = mask_resident_id(text)
    masked = mask_card_number(masked)
    masked = mask_phone_number(masked)
    return masked
