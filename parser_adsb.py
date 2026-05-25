#!/usr/bin/env python3
"""
ADS-B Message Parser Module (Renamed to avoid conflicts with built-in 'parser' module)

This module parses Mode S Extended Squitter (ADS-B) messages. It performs:
1. CRC checksum validation (using the 24-bit Mode S polynomial).
2. Downlink Format (DF) extraction (bits 1-5).
3. 24-bit ICAO aircraft address extraction (bits 9-32).
4. Type Code extraction from the ME field (bits 33-37).
"""

import sys
import re
from typing import Dict, Any, Union

MODE_S_POLY = 0xFFF409


def clean_message(hex_msg: str) -> str:
    """
    Cleans a raw Mode S hex message by removing common wrapper characters,
    whitespaces, and converting it to uppercase.
    """
    cleaned = hex_msg.strip().replace("*", "").replace(";", "").upper()
    if not re.match(r"^[0-9A-F]+$", cleaned):
        raise ValueError(
            f"Invalid characters in message: '{hex_msg}'. Hexadecimal expected."
        )
    return cleaned


def validate_crc(hex_msg: str) -> bool:
    """
    Validates the 24-bit CRC checksum of a 112-bit (14-byte) Mode S message.
    """
    cleaned = clean_message(hex_msg)
    if len(cleaned) != 28:
        raise ValueError(
            f"Invalid message length: {len(cleaned)} hex characters. Expected 28 (112 bits)."
        )

    msg_bytes = bytes.fromhex(cleaned)
    rem = 0

    for byte in msg_bytes:
        for bit_idx in range(7, -1, -1):
            bit = (byte >> bit_idx) & 1
            msb_set = (rem & 0x800000) != 0
            rem = ((rem << 1) | bit) & 0xFFFFFF
            if msb_set:
                rem ^= MODE_S_POLY

    return rem == 0


def extract_df(hex_msg: str) -> int:
    """
    Extracts the Downlink Format (DF) from bits 1-5.
    """
    cleaned = clean_message(hex_msg)
    msg_bytes = bytes.fromhex(cleaned)
    df = msg_bytes[0] >> 3
    return df


def extract_icao(hex_msg: str) -> str:
    """
    Extracts the 24-bit ICAO aircraft address from bits 9-32.
    """
    cleaned = clean_message(hex_msg)
    if len(cleaned) < 8:
        raise ValueError("Message is too short to extract ICAO address.")
    return cleaned[2:8]


def extract_type_code(hex_msg: str) -> int:
    """
    Extracts the Type Code from the ME (Message, Extended Squitter) field.
    """
    cleaned = clean_message(hex_msg)
    if len(cleaned) < 10:
        raise ValueError("Message is too short to extract Type Code.")

    df = extract_df(cleaned)
    if df not in (17, 18):
        raise ValueError(
            f"Downlink Format {df} does not contain a standard Extended Squitter ME field (expected DF 17 or 18)."
        )

    msg_bytes = bytes.fromhex(cleaned)
    type_code = msg_bytes[4] >> 3
    return type_code


def parse_adsb_message(hex_msg: str) -> Dict[str, Any]:
    """
    Convenience function that parses all required fields and validates the CRC checksum.
    """
    cleaned = clean_message(hex_msg)

    df = extract_df(cleaned)
    icao = extract_icao(cleaned)
    crc_valid = validate_crc(cleaned)

    type_code = None
    if df in (17, 18):
        type_code = extract_type_code(cleaned)

    return {
        "raw_message": cleaned,
        "downlink_format": df,
        "icao_address": icao,
        "type_code": type_code,
        "crc_valid": crc_valid,
    }


if __name__ == "__main__":
    default_msg = "8D4840D6202CC371C32CE0576098"
    input_msg = sys.argv[1] if len(sys.argv) > 1 else default_msg

    print("-" * 50)
    print("ADS-B MESSAGE PARSER DEMO")
    print("-" * 50)
    print(f"Parsing Input Message: {input_msg}")

    try:
        results = parse_adsb_message(input_msg)
        print(f"  - Cleaned Message:   {results['raw_message']}")
        print(
            f"  - CRC Checksum Valid: {results['crc_valid']} {'(PASSED)' if results['crc_valid'] else '(FAILED)'}"
        )
        print(
            f"  - Downlink Format:   {results['downlink_format']} (DF{results['downlink_format']})"
        )
        print(f"  - ICAO Address:      0x{results['icao_address']}")
        if results["type_code"] is not None:
            print(f"  - ME Type Code:      {results['type_code']}")
        else:
            print("  - ME Type Code:      N/A (Not an Extended Squitter)")
    except Exception as e:
        print(f"Error parsing message: {e}")
    print("-" * 50)
