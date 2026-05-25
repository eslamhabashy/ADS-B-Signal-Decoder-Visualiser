#!/usr/bin/env python3
"""
ADS-B Message Parser Module

This module parses Mode S Extended Squitter (ADS-B) messages. It performs:
1. CRC checksum validation (using the 24-bit Mode S polynomial).
2. Downlink Format (DF) extraction (bits 1-5).
3. 24-bit ICAO aircraft address extraction (bits 9-32).
4. Type Code extraction from the ME field (bits 33-37).
"""

import sys
import re
from typing import Dict, Any, Union

# Mode S 24-bit CRC Generator Polynomial representation
# G(x) = x^24 + x^23 + x^22 + x^21 + x^20 + x^19 + x^18 + x^16 + x^14 + x^13 + x^12 + x^11 + x^10 + x^3 + x^1 + 1
# Hexadecimal value (without the MSB/degree-24 bit): 0xFFF409
# Full hexadecimal value (with MSB/degree-24 bit): 0x1FFF409
MODE_S_POLY = 0xFFF409


def clean_message(hex_msg: str) -> str:
    """
    Cleans a raw Mode S hex message by removing common wrapper characters,
    whitespaces, and converting it to uppercase.

    SDR receivers often format messages with leading asterisks '*' and trailing
    semicolons ';'. For example, '*8D4840D6202CC371C32CE0576098;' is cleaned to
    '8D4840D6202CC371C32CE0576098'.
    """
    cleaned = hex_msg.strip().replace("*", "").replace(";", "").upper()
    
    # Validate that it contains only valid hexadecimal characters
    if not re.match(r"^[0-9A-F]+$", cleaned):
        raise ValueError(f"Invalid characters in message: '{hex_msg}'. Hexadecimal expected.")
        
    return cleaned


def validate_crc(hex_msg: str) -> bool:
    """
    Validates the 24-bit CRC checksum of a 112-bit (14-byte) Mode S message.
    
    Mode S uses cyclic parity check where the message is divided modulo-2 by the
    generator polynomial G(x). For standard ADS-B messages (Downlink Format 17),
    the parity bits are calculated such that dividing the entire error-free message
    results in a remainder of 0.
    
    Args:
        hex_msg: The 28-character hexadecimal representation of the message.
        
    Returns:
        True if the CRC checksum is valid (remainder is 0), False otherwise.
    """
    cleaned = clean_message(hex_msg)
    if len(cleaned) != 28:
        raise ValueError(f"Invalid message length: {len(cleaned)} hex characters. Expected 28 (112 bits).")
        
    msg_bytes = bytes.fromhex(cleaned)
    rem = 0
    
    # Process the message bit by bit (112 bits total)
    for byte in msg_bytes:
        for bit_idx in range(7, -1, -1):
            # Extract the current bit (MSB first)
            bit = (byte >> bit_idx) & 1
            
            # Check if the MSB of our current 24-bit remainder register is set
            msb_set = (rem & 0x800000) != 0
            
            # Shift the register left and append the new bit
            rem = ((rem << 1) | bit) & 0xFFFFFF
            
            # If the MSB was set, perform modulo-2 subtraction (XOR) with the polynomial
            if msb_set:
                rem ^= MODE_S_POLY
                
    # If there are no transmission errors, the final remainder must be 0
    return rem == 0


def extract_df(hex_msg: str) -> int:
    """
    Extracts the Downlink Format (DF) from bits 1-5.
    
    The first 5 bits of any Mode S message define the Downlink Format.
    This corresponds to the 5 Most Significant Bits (MSBs) of the first byte.
    
    Args:
        hex_msg: The hexadecimal representation of the message.
        
    Returns:
        The Downlink Format (DF) as an integer (e.g., 17 for ADS-B).
    """
    cleaned = clean_message(hex_msg)
    msg_bytes = bytes.fromhex(cleaned)
    
    # The first byte (byte 0) contains bits 1-8.
    # Shifting right by 3 discards the 3 LSBs, leaving the 5 MSBs (bits 1-5).
    df = msg_bytes[0] >> 3
    return df


def extract_icao(hex_msg: str) -> str:
    """
    Extracts the 24-bit ICAO aircraft address from bits 9-32.
    
    The ICAO address uniquely identifies the transmitting aircraft.
    In the 112-bit message structure:
    - Byte 0 (bits 1-8) contains DF and CA.
    - Bytes 1, 2, and 3 (bits 9-32) contain the 24-bit ICAO aircraft address.
    
    Args:
        hex_msg: The hexadecimal representation of the message.
        
    Returns:
        A 6-character uppercase hexadecimal string representing the ICAO address.
    """
    cleaned = clean_message(hex_msg)
    if len(cleaned) < 8:
        raise ValueError("Message is too short to extract ICAO address.")
        
    # Byte 1 corresponds to hex characters at index 2, 3
    # Byte 2 corresponds to hex characters at index 4, 5
    # Byte 3 corresponds to hex characters at index 6, 7
    # Thus, character slice [2:8] represents the 24-bit ICAO address
    return cleaned[2:8]


def extract_type_code(hex_msg: str) -> int:
    """
    Extracts the Type Code from the ME (Message, Extended Squitter) field.
    
    The ME field occupies bits 33 to 88 (56 bits, or bytes 4 to 10).
    The Type Code is located in the first 5 bits of the ME field (bits 33-37),
    which corresponds to the 5 Most Significant Bits (MSBs) of byte 4.
    
    Args:
        hex_msg: The hexadecimal representation of the message.
        
    Returns:
        The Type Code as an integer (0 to 31).
    """
    cleaned = clean_message(hex_msg)
    if len(cleaned) < 10:
        raise ValueError("Message is too short to extract Type Code.")
        
    # Verify Downlink Format contains an ME field (typically DF 17 or 18)
    df = extract_df(cleaned)
    if df not in (17, 18):
        raise ValueError(
            f"Downlink Format {df} does not contain a standard Extended Squitter ME field (expected DF 17 or 18)."
        )
        
    msg_bytes = bytes.fromhex(cleaned)
    
    # Byte index 4 corresponds to bits 33-40.
    # Shifting right by 3 discards the 3 LSBs, leaving the 5 MSBs (bits 33-37).
    type_code = msg_bytes[4] >> 3
    return type_code


def parse_adsb_message(hex_msg: str) -> Dict[str, Any]:
    """
    Convenience function that parses all required fields and validates the CRC checksum.
    
    Args:
        hex_msg: A raw hex string representing the ADS-B message.
        
    Returns:
        A dictionary containing the parsed fields and validation status.
    """
    cleaned = clean_message(hex_msg)
    
    df = extract_df(cleaned)
    icao = extract_icao(cleaned)
    crc_valid = validate_crc(cleaned)
    
    # Type code is only applicable to Extended Squitter messages (DF 17/18)
    type_code = None
    if df in (17, 18):
        type_code = extract_type_code(cleaned)
        
    return {
        "raw_message": cleaned,
        "downlink_format": df,
        "icao_address": icao,
        "type_code": type_code,
        "crc_valid": crc_valid
    }


if __name__ == "__main__":
    # If run as a script, parse command-line argument or run default demo
    default_msg = "8D4840D6202CC371C32CE0576098"
    input_msg = sys.argv[1] if len(sys.argv) > 1 else default_msg
    
    print("-" * 50)
    print("ADS-B MESSAGE PARSER DEMO")
    print("-" * 50)
    print(f"Parsing Input Message: {input_msg}")
    
    try:
        results = parse_adsb_message(input_msg)
        print(f"  - Cleaned Message:   {results['raw_message']}")
        print(f"  - CRC Checksum Valid: {results['crc_valid']} {'(PASSED)' if results['crc_valid'] else '(FAILED)'}")
        print(f"  - Downlink Format:   {results['downlink_format']} (DF{results['downlink_format']})")
        print(f"  - ICAO Address:      0x{results['icao_address']}")
        if results['type_code'] is not None:
            print(f"  - ME Type Code:      {results['type_code']}")
        else:
            print("  - ME Type Code:      N/A (Not an Extended Squitter)")
    except Exception as e:
        print(f"Error parsing message: {e}")
    print("-" * 50)
