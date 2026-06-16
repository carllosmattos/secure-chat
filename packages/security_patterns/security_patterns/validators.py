"""Validators for PII patterns to reduce false positives."""

import re


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def is_valid_cpf(value: str) -> bool:
    cpf = _digits_only(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        total = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digit = (total * 10 % 11) % 10
        if digit != int(cpf[i]):
            return False
    return True


def luhn_check(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def is_valid_credit_card(value: str) -> bool:
    digits = _digits_only(value)
    if not (13 <= len(digits) <= 19):
        return False
    return luhn_check(digits)


def is_valid_luhn_candidate(value: str) -> bool:
    return is_valid_credit_card(value)
