#!/usr/bin/env python3
"""
ADS-B CPR (Compact Position Reporting) Decoder Module

This module decodes airborne positions (Type Codes 9-18) from even/odd pairs
of Mode S Extended Squitter (ADS-B) messages.

What is CPR and why does it exist?
-----------------------------------
Compact Position Reporting (CPR) is a spatial data compression technique defined in
the ADS-B standard (RTCA DO-260B). It is used to compress the latitude and longitude
of an aircraft to fit within the limited 112-bit payload of a Mode S message.

Specifically, CPR allocates only 34 bits of the 56-bit Message (ME) payload for coordinates:
- 17 bits for the encoded latitude.
- 17 bits for the encoded longitude.

Without compression, standard single-precision floats (32 bits each) or double-precision
floats (64 bits each) would exceed or consume the entire available payload.

By partitioning the globe into latitude and longitude zones, CPR provides:
1. High Spatial Resolution: Under 5.1 meters of precision at the equator.
2. Global Decoding: Unambiguously decodes coordinates using a pair of "Even" (F=0) and
   "Odd" (F=1) messages received within a 10-second window.
3. Local Decoding: Decodes coordinates using a single message and a known reference position
   (e.g., the last recorded position) if within 180 NM.
"""

import math
import sys
from typing import Dict, Any, Tuple, Optional
from parser import clean_message, extract_df, extract_icao, extract_type_code


def nl(lat: float) -> int:
    """
    Computes the number of longitude zones (NL) at a given latitude.
    
    This calculation uses the standard formula specified in RTCA DO-260B:
    
        NL(lat) = floor( 2 * pi * arccos(1 - (1 - cos(pi / (2 * NZ))) / cos^2(pi / 180 * |lat|))^-1 )
        
    Where NZ is the number of latitude zones (NZ = 15 for Mode S).
    
    Args:
        lat: Latitude in decimal degrees.
        
    Returns:
        The integer number of longitude zones (between 1 and 59).
    """
    abs_lat = abs(lat)
    
    # At latitudes >= 87.0 degrees, there is only 1 longitude zone
    if abs_lat >= 87.0:
        return 1
        
    nz = 15.0
    numerator = 1.0 - math.cos(math.pi / (2.0 * nz))
    denominator = math.cos(math.radians(abs_lat)) ** 2
    
    # Calculate the argument for arccos
    acos_arg = 1.0 - (numerator / denominator)
    
    # Clamp acos_arg to [-1.0, 1.0] to prevent domain errors due to float imprecision
    if acos_arg < -1.0:
        acos_arg = -1.0
    elif acos_arg > 1.0:
        acos_arg = 1.0
        
    val = (2.0 * math.pi) * (math.acos(acos_arg) ** -1)
    return int(math.floor(val))


def decode_altitude(me_field: int) -> Optional[int]:
    """
    Decodes the 12-bit barometric altitude field from the ME payload.
    
    The altitude occupies bits 9 to 20 of the ME field (which corresponds to
    shifting right by 36 and masking with 0xFFF from the 56-bit integer).
    
    The 8th bit of this field (bit 48 of the Mode S message) is the Q-bit:
    - Q = 1: 25 ft resolution. The altitude is computed as: (N * 25) - 1000,
             where N is the 11-bit value obtained by removing the Q-bit.
    - Q = 0: 100 ft resolution. The altitude is encoded using Gillham code (Gray code).
    
    Args:
        me_field: The 56-bit ME payload as an integer.
        
    Returns:
        The altitude in feet as an integer, or None if it cannot be decoded.
    """
    # Extract the 12-bit altitude field (bits 9-20 of ME)
    alt_field = (me_field >> 36) & 0xFFF
    
    # The Q-bit is at bit 4 of the 12-bit field (bit index 4 from the right)
    q_bit = (alt_field >> 4) & 1
    
    if q_bit == 1:
        # 25-foot resolution: Remove the Q-bit (bit 4) to reconstruct 11-bit value N
        # N consists of the upper 7 bits (bits 11-5) and the lower 4 bits (bits 3-0)
        n = ((alt_field >> 5) << 4) | (alt_field & 0xF)
        return n * 25 - 1000
    else:
        # 100-foot resolution (Gillham Code / Gray Code)
        # Note: Implementing the Gillham gray conversion or returning None if not implemented.
        # Let's implement the standard Gray code conversion for Gillham.
        return decode_gillham_altitude(alt_field)


def _gray2bin(gray_val: int, num_bits: int) -> int:
    """Converts a Gray code integer to a standard binary integer."""
    mask = gray_val >> 1
    val = gray_val
    while mask != 0:
        val ^= mask
        mask >>= 1
    return val


def decode_gillham_altitude(alt_field: int) -> Optional[int]:
    """
    Decodes a 100 ft resolution altitude field encoded in Gillham/Gray code format.
    
    The 12 bits of the altitude field (ignoring the Q-bit which is 0) map to
    Gillham bits. Since Gillham to altitude mapping has specific bit-interleaving,
    we map it using standard Gillham-to-Gray-to-altitude decoding.
    
    For simplicity and reliability, if we encounter standard Gillham, we reconstruct
    the bits (D1, D2, D4, A1, A2, A4, B1, B2, B4, C1, C2, C4) and decode.
    """
    # Mode S transponder Gillham bits layout inside the 12-bit altitude field:
    # alt_field = [C1, A1, C2, A2, C4, A4, zero, B1, Q, B2, D2, B4] (MSB to LSB)
    # Wait, the 12 bits in alt_field are:
    # Bit: 11  10  9   8   7   6   5   4   3   2   1   0
    # Val: C1  A1  C2  A2  C4  A4  0   B1  Q   B2  D2  B4
    # (Since Q-bit at bit 4 is 0)
    
    c1 = (alt_field >> 11) & 1
    a1 = (alt_field >> 10) & 1
    c2 = (alt_field >> 9) & 1
    a2 = (alt_field >> 8) & 1
    c4 = (alt_field >> 7) & 1
    a4 = (alt_field >> 6) & 1
    b1 = (alt_field >> 5) & 1  # Note: bit 5 is B1
    # bit 4 is Q (which is 0)
    b2 = (alt_field >> 3) & 1
    d2 = (alt_field >> 2) & 1
    b4 = (alt_field >> 1) & 1
    d4 = alt_field & 1         # LSB is D4 (or B4 depending on layout)
    
    # We combine them to form the 500-foot interval Gray code (D2, D4, A1, A2, A4, B1, B2, B4)
    # and the 100-foot interval Gray code (C1, C2, C4)
    # Due to complexity and hardware-specific mappings of Gillham code,
    # the standard conversion utilizes a bit mapping.
    # Let's implement the standard lookup/mapping logic.
    # If the user's data does not use Gillham, Q=1 is the most common for ADS-B.
    # We will provide a clean decoding logic for 100ft resolution.
    
    # We construct the 500 ft Gray code value:
    # bits: D2 D4 A1 A2 A4 B1 B2 B4
    gray_500 = (d2 << 7) | (d4 << 6) | (a1 << 5) | (a2 << 4) | (a4 << 3) | (b1 << 2) | (b2 << 1) | b4
    bin_500 = _gray2bin(gray_500, 8)
    
    # The C-bits (C1, C2, C4) represent the 100 ft increments within the 500 ft interval.
    gray_100 = (c1 << 2) | (c2 << 1) | c4
    bin_100 = _gray2bin(gray_100, 3)
    
    # Standard Gillham mapping check:
    # bin_100 maps to 100 ft steps (-200, -100, 0, 100, 200)
    # If 500 ft block is odd, the 100 ft Gray code is reflected (inverted)
    if bin_100 == 0 or bin_100 == 5 or bin_100 == 6:
        # Invalid C-bits values according to transponder spec
        return None
        
    if bin_100 == 7:
        bin_100 = 5
        
    # Parity check
    if bin_500 % 2 != 0:
        bin_100 = 6 - bin_100
        
    # Calculate offset
    # 500 ft Gray code 0 corresponds to -1000 ft, etc.
    altitude = (bin_500 * 500) + (bin_100 * 100) - 1300
    return altitude


def decode_airborne_position(even_msg: str, odd_msg: str) -> Dict[str, Any]:
    """
    Decodes the global latitude and longitude from a pair of Even and Odd ADS-B messages.
    
    Args:
        even_msg: Hexadecimal representation of the Even frame (F=0).
        odd_msg: Hexadecimal representation of the Odd frame (F=1).
        
    Returns:
        A dictionary containing the decoded coordinates and aircraft metadata:
        {
            "icao_address": str,
            "latitude_even": float,
            "longitude_even": float,
            "latitude_odd": float,
            "longitude_odd": float,
            "altitude_even": int,
            "altitude_odd": int,
            "type_code": int
        }
        
    Raises:
        ValueError if the messages are invalid, from different aircraft, or cannot
        be globally decoded.
    """
    # 1. Clean and normalize strings
    clean_even = clean_message(even_msg)
    clean_odd = clean_message(odd_msg)
    
    # 2. Basic validations
    if len(clean_even) != 28 or len(clean_odd) != 28:
        raise ValueError("Both messages must be exactly 28 hex characters (112 bits).")
        
    # Validate Downlink Format (DF17 or DF18)
    df_even = extract_df(clean_even)
    df_odd = extract_df(clean_odd)
    if df_even not in (17, 18) or df_odd not in (17, 18):
        raise ValueError("Both messages must be Downlink Format 17 or 18 (Extended Squitter).")
        
    # Validate Type Code (Airborne Position is TC 9-18)
    tc_even = extract_type_code(clean_even)
    tc_odd = extract_type_code(clean_odd)
    if not (9 <= tc_even <= 18) or not (9 <= tc_odd <= 18):
        raise ValueError(
            f"Invalid Type Codes (Even: {tc_even}, Odd: {tc_odd}). Expected 9 to 18 for Airborne Position."
        )
        
    # Verify both messages are from the same aircraft
    icao_even = extract_icao(clean_even)
    icao_odd = extract_icao(clean_odd)
    if icao_even != icao_odd:
        raise ValueError(
            f"ICAO address mismatch: Even message is {icao_even}, Odd message is {icao_odd}."
        )
        
    # 3. Parse ME Fields
    # ME field is bytes 4 to 10 inclusive (index 8 to 22 in hex string)
    me_even = int(clean_even[8:22], 16)
    me_odd = int(clean_odd[8:22], 16)
    
    # Extract CPR formats (F-flag is bit 22 of ME field, i.e., bit 34 from LSB)
    f_even = (me_even >> 34) & 1
    f_odd = (me_odd >> 34) & 1
    
    # Verify that one message is Even and the other is Odd
    if f_even == f_odd:
        raise ValueError(
            f"Both messages have the same CPR format flag (F={f_even}). "
            f"Global decoding requires one Even (F=0) and one Odd (F=1) message."
        )
        
    # Standardize roles: assign variables so index 0 = Even and index 1 = Odd
    # even_me is the ME field of the Even message; odd_me is the ME field of the Odd message
    if f_even == 0:
        even_val_me = me_even
        odd_val_me = me_odd
    else:
        even_val_me = me_odd
        odd_val_me = me_even
        
    # Extract 17-bit encoded latitude and longitude values
    # Latitude is bits 23-39 of ME (shift by 17, mask 17 bits: 0x1FFFF)
    # Longitude is bits 40-56 of ME (mask 17 bits: 0x1FFFF)
    yz_even = (even_val_me >> 17) & 0x1FFFF
    xz_even = even_val_me & 0x1FFFF
    
    yz_odd = (odd_val_me >> 17) & 0x1FFFF
    xz_odd = odd_val_me & 0x1FFFF
    
    # 2^17 = 131072
    nb2 = 131072.0
    
    # --- Latitude Decoding ---
    # Calculate latitude index j
    j = math.floor(((59.0 * yz_even - 60.0 * yz_odd) / nb2) + 0.5)
    
    # Compute relative latitudes
    rlat_even = 6.0 * ((j % 60) + yz_even / nb2)
    rlat_odd = (360.0 / 59.0) * ((j % 59) + yz_odd / nb2)
    
    # Check for Southern Hemisphere (values >= 270 represent negative latitudes)
    if rlat_even >= 270.0:
        rlat_even -= 360.0
    if rlat_odd >= 270.0:
        rlat_odd -= 360.0
        
    # Check consistency of Latitude Zones (NL must be equal)
    nl_even = nl(rlat_even)
    nl_odd = nl(rlat_odd)
    if nl_even != nl_odd:
        raise ValueError(
            f"Decoded latitudes ({rlat_even:.4f}, {rlat_odd:.4f}) belong to different zones "
            f"(NL_even: {nl_even}, NL_odd: {nl_odd}). Cannot decode position."
        )
        
    nl_val = nl_even
    
    # --- Longitude Decoding ---
    # Calculate longitude index m
    m = math.floor(((xz_even * (nl_val - 1.0) - xz_odd * nl_val) / nb2) + 0.5)
    
    # Decode longitude using Even frame
    ne = max(nl_val, 1)
    dlon_even = 360.0 / ne
    rlon_even = dlon_even * ((m % ne) + xz_even / nb2)
    if rlon_even >= 180.0:
        rlon_even -= 360.0
        
    # Decode longitude using Odd frame
    no = max(nl_val - 1, 1)
    dlon_odd = 360.0 / no
    rlon_odd = dlon_odd * ((m % no) + xz_odd / nb2)
    if rlon_odd >= 180.0:
        rlon_odd -= 360.0
        
    # Decode Altitude from both frames
    alt_even = decode_altitude(me_even)
    alt_odd = decode_altitude(me_odd)
    
    # Assign the output depending on which message was passed as even_msg / odd_msg
    if f_even == 0:
        return {
            "icao_address": icao_even,
            "latitude_even": rlat_even,
            "longitude_even": rlon_even,
            "latitude_odd": rlat_odd,
            "longitude_odd": rlon_odd,
            "altitude_even": alt_even,
            "altitude_odd": alt_odd,
            "type_code": tc_even
        }
    else:
        return {
            "icao_address": icao_even,
            "latitude_even": rlat_odd,
            "longitude_even": rlon_odd,
            "latitude_odd": rlat_even,
            "longitude_odd": rlon_even,
            "altitude_even": alt_odd,
            "altitude_odd": alt_even,
            "type_code": tc_even
        }


if __name__ == "__main__":
    # Test vector pair for Cebu Pacific Air Airbus A319 (RP-C3191)
    # Even Frame: F=0
    test_even = "8D75804B580FF2CF7E9BA6F701D0"
    # Odd Frame: F=1
    test_odd = "8D75804B580FF6B283EB7A157117"
    
    print("-" * 65)
    print("ADS-B CPR DECODER DEMO (RP-C3191 Cebu Pacific Air)")
    print("-" * 65)
    print(f"Even Msg: {test_even}")
    print(f"Odd Msg:  {test_odd}")
    
    try:
        res = decode_airborne_position(test_even, test_odd)
        print("\nDecoded Global Position:")
        print(f"  - ICAO Address:       0x{res['icao_address']}")
        print(f"  - Type Code:          {res['type_code']}")
        print(f"  - Even Frame Position: ({res['latitude_even']:.6f}, {res['longitude_even']:.6f})")
        print(f"  - Odd Frame Position:  ({res['latitude_odd']:.6f}, {res['longitude_odd']:.6f})")
        print(f"  - Even Frame Altitude: {res['altitude_even']} ft")
        print(f"  - Odd Frame Altitude:  {res['altitude_odd']} ft")
        print(f"  - Distance Moved:      Approx. {abs(res['latitude_even'] - res['latitude_odd'])*111.1:.3f} km north-south")
    except Exception as err:
        print(f"Error decoding CPR pair: {err}")
    print("-" * 65)
