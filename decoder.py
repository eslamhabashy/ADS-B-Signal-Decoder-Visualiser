#!/usr/bin/env python3
"""
ADS-B CPR (Compact Position Reporting) and Velocity Decoder Module

This module decodes:
1. Airborne positions (Type Codes 9-18) from even/odd Extended Squitter (ADS-B) messages.
2. Airborne velocities (Type Code 19) including Ground Speed and Airspeed.
"""

import math
import sys
from typing import Dict, Any, Tuple, Optional
from parser_adsb import clean_message, extract_df, extract_icao, extract_type_code


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
    """
    c1 = (alt_field >> 11) & 1
    a1 = (alt_field >> 10) & 1
    c2 = (alt_field >> 9) & 1
    a2 = (alt_field >> 8) & 1
    c4 = (alt_field >> 7) & 1
    a4 = (alt_field >> 6) & 1
    b1 = (alt_field >> 5) & 1
    b2 = (alt_field >> 3) & 1
    d2 = (alt_field >> 2) & 1
    b4 = (alt_field >> 1) & 1
    d4 = alt_field & 1

    # We construct the 500 ft Gray code value:
    # bits: D2 D4 A1 A2 A4 B1 B2 B4
    gray_500 = (
        (d2 << 7)
        | (d4 << 6)
        | (a1 << 5)
        | (a2 << 4)
        | (a4 << 3)
        | (b1 << 2)
        | (b2 << 1)
        | b4
    )
    bin_500 = _gray2bin(gray_500, 8)

    # The C-bits (C1, C2, C4) represent the 100 ft increments within the 500 ft interval.
    gray_100 = (c1 << 2) | (c2 << 1) | c4
    bin_100 = _gray2bin(gray_100, 3)

    if bin_100 == 0 or bin_100 == 5 or bin_100 == 6:
        return None

    if bin_100 == 7:
        bin_100 = 5

    # Parity check
    if bin_500 % 2 != 0:
        bin_100 = 6 - bin_100

    # Calculate offset
    altitude = (bin_500 * 500) + (bin_100 * 100) - 1300
    return altitude


def decode_airborne_position(even_msg: str, odd_msg: str) -> Dict[str, Any]:
    """
    Decodes the global latitude and longitude from a pair of Even and Odd ADS-B messages.
    """
    clean_even = clean_message(even_msg)
    clean_odd = clean_message(odd_msg)

    if len(clean_even) != 28 or len(clean_odd) != 28:
        raise ValueError("Both messages must be exactly 28 hex characters (112 bits).")

    df_even = extract_df(clean_even)
    df_odd = extract_df(clean_odd)
    if df_even not in (17, 18) or df_odd not in (17, 18):
        raise ValueError(
            "Both messages must be Downlink Format 17 or 18 (Extended Squitter)."
        )

    tc_even = extract_type_code(clean_even)
    tc_odd = extract_type_code(clean_odd)
    if not (9 <= tc_even <= 18) or not (9 <= tc_odd <= 18):
        raise ValueError(
            f"Invalid Type Codes (Even: {tc_even}, Odd: {tc_odd}). Expected 9 to 18 for Airborne Position."
        )

    icao_even = extract_icao(clean_even)
    icao_odd = extract_icao(clean_odd)
    if icao_even != icao_odd:
        raise ValueError(
            f"ICAO address mismatch: Even message is {icao_even}, Odd message is {icao_odd}."
        )

    me_even = int(clean_even[8:22], 16)
    me_odd = int(clean_odd[8:22], 16)

    f_even = (me_even >> 34) & 1
    f_odd = (me_odd >> 34) & 1

    if f_even == f_odd:
        raise ValueError(
            f"Both messages have the same CPR format flag (F={f_even}). "
            f"Global decoding requires one Even (F=0) and one Odd (F=1) message."
        )

    if f_even == 0:
        even_val_me = me_even
        odd_val_me = me_odd
    else:
        even_val_me = me_odd
        odd_val_me = me_even

    yz_even = (even_val_me >> 17) & 0x1FFFF
    xz_even = even_val_me & 0x1FFFF

    yz_odd = (odd_val_me >> 17) & 0x1FFFF
    xz_odd = odd_val_me & 0x1FFFF

    nb2 = 131072.0

    # Calculate latitude index j
    j = math.floor(((59.0 * yz_even - 60.0 * yz_odd) / nb2) + 0.5)

    # Compute relative latitudes
    rlat_even = 6.0 * ((j % 60) + yz_even / nb2)
    rlat_odd = (360.0 / 59.0) * ((j % 59) + yz_odd / nb2)

    if rlat_even >= 270.0:
        rlat_even -= 360.0
    if rlat_odd >= 270.0:
        rlat_odd -= 360.0

    nl_even = nl(rlat_even)
    nl_odd = nl(rlat_odd)
    if nl_even != nl_odd:
        raise ValueError(
            f"Decoded latitudes ({rlat_even:.4f}, {rlat_odd:.4f}) belong to different zones "
            f"(NL_even: {nl_even}, NL_odd: {nl_odd}). Cannot decode position."
        )

    nl_val = nl_even

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

    alt_even = decode_altitude(me_even)
    alt_odd = decode_altitude(me_odd)

    if f_even == 0:
        return {
            "icao_address": icao_even,
            "latitude_even": rlat_even,
            "longitude_even": rlon_even,
            "latitude_odd": rlat_odd,
            "longitude_odd": rlon_odd,
            "altitude_even": alt_even,
            "altitude_odd": alt_odd,
            "type_code": tc_even,
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
            "type_code": tc_even,
        }


def decode_airborne_velocity(hex_msg: str) -> Dict[str, Any]:
    """
    Decodes the airborne velocity information (Type Code 19) from an ADS-B message.

    This function parses subsonic and supersonic ground speed (subtypes 1 & 2)
    and subsonic and supersonic airspeed (subtypes 3 & 4). It also decodes
    vertical rate and GNSS/baro altitude difference.

    Args:
        hex_msg: Hexadecimal representation of the message.

    Returns:
        A dictionary containing:
        {
            "icao_address": str,
            "subtype": int,
            "speed": float,              # Ground speed or airspeed in knots
            "heading": float,            # Track angle or heading in degrees (None if unavailable)
            "speed_type": str,           # 'Ground Speed', 'True Airspeed', or 'Indicated Airspeed'
            "east_west_velocity": float,  # E-W component (knots, signed, positive = East), or None
            "north_south_velocity": float,# N-S component (knots, signed, positive = North), or None
            "vertical_rate": int,        # Vertical rate in ft/min (signed, positive = Up), or None
            "vertical_rate_source": str,  # 'GNSS' or 'Barometric', or None
            "altitude_difference": int    # Difference between GNSS and Baro altitude in feet, or None
        }
    """
    cleaned = clean_message(hex_msg)

    if len(cleaned) != 28:
        raise ValueError("Message must be exactly 28 hex characters (112 bits).")

    df = extract_df(cleaned)
    if df not in (17, 18):
        raise ValueError(
            "Message must be Downlink Format 17 or 18 (Extended Squitter)."
        )

    tc = extract_type_code(cleaned)
    if tc != 19:
        raise ValueError(f"Invalid Type Code: {tc}. Expected 19 for Airborne Velocity.")

    icao = extract_icao(cleaned)

    # ME field (56 bits)
    me = int(cleaned[8:22], 16)

    # 1. Extract Subtype (bits 6-8 of ME, which is bits 48-50 from LSB)
    subtype = (me >> 48) & 0x7

    # 2. Extract vertical rate fields (common to all subtypes)
    # VrSrc: bit 36 of ME (index 20)
    vr_src_bit = (me >> 20) & 1
    vr_src = "Barometric" if vr_src_bit == 1 else "GNSS"

    # Svr (Sign): bit 37 of ME (index 19)
    vr_sign = (me >> 19) & 1

    # VR magnitude: bits 38-46 of ME (9 bits, index 10)
    vr_val = (me >> 10) & 0x1FF

    if vr_val == 0:
        vertical_rate = None
        vr_src = None
    else:
        # Rate is (vr_val - 1) * 64
        vertical_rate = (vr_val - 1) * 64
        if vr_sign == 1:
            vertical_rate = -vertical_rate

    # 3. Extract altitude difference fields (common to all subtypes)
    # SDif (Sign): bit 49 of ME (index 7)
    diff_sign = (me >> 7) & 1
    # dAlt magnitude: bits 50-56 of ME (7 bits, index 0)
    diff_val = me & 0x7F

    if diff_val == 0:
        alt_diff = None
    else:
        # Difference is (diff_val - 1) * 25
        alt_diff = (diff_val - 1) * 25
        if diff_sign == 1:
            alt_diff = -alt_diff

    # Initialize outputs
    speed = 0.0
    heading = None
    speed_type = ""
    ew_vel = None
    ns_vel = None

    # 4. Decode sub-type specific fields (bits 14-35 of ME, 22 bits)
    if subtype in (1, 2):
        # Subtype 1 & 2: Ground Speed
        # EW direction: bit 14 of ME (index 42)
        ew_dir = (me >> 42) & 1
        # EW velocity: bits 15-24 of ME (10 bits, index 32)
        ew_val = (me >> 32) & 0x3FF
        # NS direction: bit 25 of ME (index 31)
        ns_dir = (me >> 31) & 1
        # NS velocity: bits 26-35 of ME (10 bits, index 21)
        ns_val = (me >> 21) & 0x3FF

        resolution = 1.0 if subtype == 1 else 4.0
        speed_type = "Ground Speed"

        if ew_val > 0:
            ew_vel = (ew_val - 1) * resolution
            if ew_dir == 1:
                ew_vel = -ew_vel
        else:
            ew_vel = None

        if ns_val > 0:
            ns_vel = (ns_val - 1) * resolution
            if ns_dir == 1:
                ns_vel = -ns_vel
        else:
            ns_vel = None

        # Compute Ground Speed and Heading from vectors
        if ew_vel is not None and ns_vel is not None:
            speed = math.sqrt(ew_vel**2 + ns_vel**2)
            heading = math.degrees(math.atan2(ew_vel, ns_vel))
            if heading < 0:
                heading += 360.0
        else:
            speed = 0.0
            heading = None

    elif subtype in (3, 4):
        # Subtype 3 & 4: Airspeed
        # Heading Status: bit 14 of ME (index 42)
        hdg_status = (me >> 42) & 1
        # Heading: bits 15-24 of ME (10 bits, index 32)
        hdg_val = (me >> 32) & 0x3FF
        # Airspeed Type: bit 25 of ME (index 31) (0 = IAS, 1 = TAS)
        as_type = (me >> 31) & 1
        speed_type = "True Airspeed" if as_type == 1 else "Indicated Airspeed"
        # Airspeed: bits 26-35 of ME (10 bits, index 21)
        as_val = (me >> 21) & 0x3FF

        resolution = 1.0 if subtype == 3 else 4.0

        if hdg_status == 1:
            heading = hdg_val * 360.0 / 1024.0
        else:
            heading = None

        if as_val > 0:
            speed = (as_val - 1) * resolution
        else:
            speed = 0.0

        # Decompose speed & heading into components
        if heading is not None and speed > 0:
            hdg_rad = math.radians(heading)
            ew_vel = speed * math.sin(hdg_rad)
            ns_vel = speed * math.cos(hdg_rad)

    return {
        "icao_address": icao,
        "subtype": subtype,
        "speed": speed,
        "heading": heading,
        "speed_type": speed_type,
        "east_west_velocity": ew_vel,
        "north_south_velocity": ns_vel,
        "vertical_rate": vertical_rate,
        "vertical_rate_source": vr_src,
        "altitude_difference": alt_diff,
    }


if __name__ == "__main__":
    # --- Part 1: Position CPR decoding ---
    # Test vector pair for Cebu Pacific Air Airbus A319 (RP-C3191)
    test_even = "8D75804B580FF2CF7E9BA6F701D0"
    test_odd = "8D75804B580FF6B283EB7A157117"

    print("-" * 65)
    print("ADS-B POSITION & CPR DECODER DEMO (RP-C3191)")
    print("-" * 65)
    print(f"Even Msg: {test_even}")
    print(f"Odd Msg:  {test_odd}")

    try:
        pos_res = decode_airborne_position(test_even, test_odd)
        print("\nDecoded Global Position:")
        print(f"  - ICAO Address:       0x{pos_res['icao_address']}")
        print(f"  - Type Code:          {pos_res['type_code']}")
        print(
            f"  - Even Frame Position: ({pos_res['latitude_even']:.6f}, {pos_res['longitude_even']:.6f})"
        )
        print(
            f"  - Odd Frame Position:  ({pos_res['latitude_odd']:.6f}, {pos_res['longitude_odd']:.6f})"
        )
        print(f"  - Even Frame Altitude: {pos_res['altitude_even']} ft")
        print(f"  - Odd Frame Altitude:  {pos_res['altitude_odd']} ft")
        print(
            f"  - Distance Moved:      Approx. {abs(pos_res['latitude_even'] - pos_res['latitude_odd'])*111.1:.3f} km north-south"
        )
    except Exception as err:
        print(f"Error decoding CPR pair: {err}")

    # --- Part 2: Velocity Type Code 19 decoding ---
    print("\n" + "-" * 65)
    print("ADS-B VELOCITY DECODER DEMO (Type Code 19)")
    print("-" * 65)

    # Subtype 1 Ground Speed message
    sub1_test = "8D75804B99006599200000000000"
    # Subtype 3 Airspeed message
    sub3_test = "8D75804B9B0600A5A00000000000"

    for label, msg in [
        ("Subtype 1 (Ground Speed)", sub1_test),
        ("Subtype 3 (Airspeed)", sub3_test),
    ]:
        print(f"\nDecoding {label}: {msg}")
        try:
            vel_res = decode_airborne_velocity(msg)
            print(f"  - Subtype:            {vel_res['subtype']}")
            print(f"  - Speed Type:         {vel_res['speed_type']}")
            print(f"  - Speed Magnitude:    {vel_res['speed']:.2f} knots")
            if vel_res["heading"] is not None:
                print(f"  - Heading/Track:      {vel_res['heading']:.2f}°")
            else:
                print(f"  - Heading/Track:      N/A")
            if vel_res["east_west_velocity"] is not None:
                print(
                    f"  - E-W component:      {vel_res['east_west_velocity']:.2f} knots"
                )
            if vel_res["north_south_velocity"] is not None:
                print(
                    f"  - N-S component:      {vel_res['north_south_velocity']:.2f} knots"
                )
            if vel_res["vertical_rate"] is not None:
                print(
                    f"  - Vertical Rate:      {vel_res['vertical_rate']} ft/min ({vel_res['vertical_rate_source']})"
                )
            if vel_res["altitude_difference"] is not None:
                print(f"  - Alt Difference:     {vel_res['altitude_difference']} ft")
        except Exception as err:
            print(f"Error decoding velocity: {err}")
    print("-" * 65)
