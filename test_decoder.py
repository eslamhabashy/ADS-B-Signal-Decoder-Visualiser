#!/usr/bin/env python3
import unittest
from decoder import nl, decode_altitude, decode_airborne_position


class TestADSBDecoder(unittest.TestCase):
    
    def setUp(self):
        # Cebu Pacific Air RP-C3191 test vector pair
        self.even_msg = "8D75804B580FF2CF7E9BA6F701D0"
        self.odd_msg = "8D75804B580FF6B283EB7A157117"
        
        # Corrupted or mismatched inputs
        self.wrong_icao_odd = "8D75804C580FF6B283EB7A157117"  # ICAO changed to 75804C
        self.wrong_tc_odd = "8D75804B280FF6B283EB7A157117"    # TC changed to 5 (Surface Position)

    def test_nl_function(self):
        # Test values for NL function at various latitudes
        self.assertEqual(nl(0.0), 59)      # Equator
        self.assertEqual(nl(10.215), 59)   # Near Cebu (10.2 degrees)
        self.assertEqual(nl(51.5), 37)     # Near London (51.5 degrees)
        self.assertEqual(nl(86.9), 2)      # Just below 87 degrees
        self.assertEqual(nl(87.0), 1)      # Boundary
        self.assertEqual(nl(89.9), 1)      # Near North Pole
        self.assertEqual(nl(-51.5), 37)    # Negative latitude (London South equivalent)
        self.assertEqual(nl(-89.9), 1)    # South Pole

    def test_decode_altitude(self):
        # 1. 25-foot resolution (Q = 1)
        # Even ME payload is 0x580FF2CF7E9BA6
        # alt_field: 0b11111111 (255), Q-bit (bit 4) is 1.
        # Upper 7 bits: 7 (0b111). Lower 4 bits: 15 (0b1111).
        # N = 127. Altitude = 127 * 25 - 1000 = 2175 ft.
        even_me = 0x580FF2CF7E9BA6
        self.assertEqual(decode_altitude(even_me), 2175)
        
        # Test another 25 ft case: 0x5808C...
        # 12-bit field is 0x08C (0b0000 1000 1100). Q-bit (bit 4) is 0b0.
        # This will route to Gillham since Q is 0.

    def test_decode_airborne_position(self):
        # Global position decoding for valid pair
        res = decode_airborne_position(self.even_msg, self.odd_msg)
        
        self.assertEqual(res["icao_address"], "75804B")
        self.assertEqual(res["type_code"], 11)
        
        # Assert latitudes are close to 10.215
        self.assertAlmostEqual(res["latitude_even"], 10.215775, places=5)
        self.assertAlmostEqual(res["latitude_odd"], 10.216214, places=5)
        
        # Assert longitudes are close to 123.888
        self.assertAlmostEqual(res["longitude_even"], 123.888819, places=5)
        self.assertAlmostEqual(res["longitude_odd"], 123.889129, places=5)
        
        # Assert altitudes
        self.assertEqual(res["altitude_even"], 2175)
        self.assertEqual(res["altitude_odd"], 2175)

    def test_decode_airborne_position_errors(self):
        # Mismatched ICAO address should raise ValueError
        with self.assertRaises(ValueError):
            decode_airborne_position(self.even_msg, self.wrong_icao_odd)
            
        # Mismatched or invalid Type Code should raise ValueError
        with self.assertRaises(ValueError):
            decode_airborne_position(self.even_msg, self.wrong_tc_odd)
            
        # Passing two even frames should raise ValueError
        with self.assertRaises(ValueError):
            decode_airborne_position(self.even_msg, self.even_msg)


if __name__ == "__main__":
    unittest.main()
