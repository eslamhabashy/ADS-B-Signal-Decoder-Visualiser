#!/usr/bin/env python3
import unittest
from parser import clean_message, validate_crc, extract_df, extract_icao, extract_type_code, parse_adsb_message


class TestADSBParser(unittest.TestCase):
    
    def setUp(self):
        # The standard sample message from the prompt
        self.sample_msg = "8D4840D6202CC371C32CE0576098"
        # Same message wrapped in common SDR prefix/suffix
        self.wrapped_msg = "*8D4840D6202CC371C32CE0576098;"
        # Message with a single corrupted bit to test CRC failure (changed last digit 8 to 9)
        self.corrupted_msg = "8D4840D6202CC371C32CE0576099"

    def test_clean_message(self):
        self.assertEqual(clean_message(self.sample_msg), "8D4840D6202CC371C32CE0576098")
        self.assertEqual(clean_message(self.wrapped_msg), "8D4840D6202CC371C32CE0576098")
        self.assertEqual(clean_message("  *8d4840d6202cc371c32ce0576098;  "), "8D4840D6202CC371C32CE0576098")
        
        with self.assertRaises(ValueError):
            clean_message("8D4840D6202CC371C32CE057609G")  # 'G' is not valid hex

    def test_validate_crc(self):
        self.assertTrue(validate_crc(self.sample_msg))
        self.assertTrue(validate_crc(self.wrapped_msg))
        self.assertFalse(validate_crc(self.corrupted_msg))
        
        # Test length validation
        with self.assertRaises(ValueError):
            validate_crc("8D4840D")  # Too short

    def test_extract_df(self):
        self.assertEqual(extract_df(self.sample_msg), 17)
        self.assertEqual(extract_df(self.wrapped_msg), 17)
        
        # Test custom message: DF is determined by first 5 bits of first byte.
        # 0x00 has first byte 00000000 -> DF 0
        # 0xF0 has first byte 11110000 -> DF 30
        self.assertEqual(extract_df("00" + "0" * 26), 0)
        self.assertEqual(extract_df("F0" + "0" * 26), 30)

    def test_extract_icao(self):
        self.assertEqual(extract_icao(self.sample_msg), "4840D6")
        self.assertEqual(extract_icao(self.wrapped_msg), "4840D6")

    def test_extract_type_code(self):
        self.assertEqual(extract_type_code(self.sample_msg), 4)
        self.assertEqual(extract_type_code(self.wrapped_msg), 4)
        
        # Non-Extended Squitter DF should raise ValueError (e.g., DF 11 message)
        # Message beginning with '5D' -> DF 11 (01011101 -> 01011 = 11)
        df_11_msg = "5D4840D6202CC371C32CE0576098"
        with self.assertRaises(ValueError):
            extract_type_code(df_11_msg)

    def test_parse_adsb_message(self):
        result = parse_adsb_message(self.sample_msg)
        self.assertEqual(result["downlink_format"], 17)
        self.assertEqual(result["icao_address"], "4840D6")
        self.assertEqual(result["type_code"], 4)
        self.assertTrue(result["crc_valid"])


if __name__ == "__main__":
    unittest.main()
