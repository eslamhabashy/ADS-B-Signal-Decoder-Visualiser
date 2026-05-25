#!/usr/bin/env python3
import unittest
import math
from decoder import nl, decode_altitude, decode_airborne_position, decode_airborne_velocity


class TestADSBDecoder(unittest.TestCase):
    
    def setUp(self):
        # Cebu Pacific Air RP-C3191 test vector pair for CPR
        self.even_msg = "8D75804B580FF2CF7E9BA6F701D0"
        self.odd_msg = "8D75804B580FF6B283EB7A157117"
        
        # Corrupted or mismatched inputs for CPR
        self.wrong_icao_odd = "8D75804C580FF6B283EB7A157117"
        self.wrong_tc_odd = "8D75804B280FF6B283EB7A157117"
        
        # Airborne Velocity test vectors
        self.sub1_velocity_msg = "8D75804B99006599200000000000"
        self.sub3_velocity_msg = "8D75804B9B0600A5A00000000000"

    def test_nl_function(self):
        # Test values for NL function at various latitudes
        self.assertEqual(nl(0.0), 59)      # Equator
        self.assertEqual(nl(10.215), 59)   # Near Cebu (10.2 degrees)
        self.assertEqual(nl(51.5), 37)     # Near London (51.5 degrees)
        self.assertEqual(nl(86.9), 2)      # Just below 87 degrees
        self.assertEqual(nl(87.0), 1)      # Boundary
        self.assertEqual(nl(89.9), 1)      # Near North Pole
        self.assertEqual(nl(-51.5), 37)    # Negative latitude
        self.assertEqual(nl(-89.9), 1)    # South Pole

    def test_decode_altitude(self):
        # 25-foot resolution (Q = 1)
        even_me = 0x580FF2CF7E9BA6
        self.assertEqual(decode_altitude(even_me), 2175)

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
        with self.assertRaises(ValueError):
            decode_airborne_position(self.even_msg, self.wrong_icao_odd)
        with self.assertRaises(ValueError):
            decode_airborne_position(self.even_msg, self.wrong_tc_odd)
        with self.assertRaises(ValueError):
            decode_airborne_position(self.even_msg, self.even_msg)

    def test_decode_airborne_velocity_subtype_1(self):
        # Test ground speed decoding (Subtype 1)
        res = decode_airborne_velocity(self.sub1_velocity_msg)
        self.assertEqual(res["icao_address"], "75804B")
        self.assertEqual(res["subtype"], 1)
        self.assertEqual(res["speed_type"], "Ground Speed")
        
        # Assert East-West and North-South components
        self.assertEqual(res["east_west_velocity"], 100.0)      # East
        self.assertEqual(res["north_south_velocity"], -200.0)   # South
        
        # Speed should be sqrt(100^2 + 200^2) = sqrt(50000) ~ 223.6068
        self.assertAlmostEqual(res["speed"], math.sqrt(50000.0), places=4)
        
        # Track heading should be atan2(100, -200) ~ 153.4349 degrees
        expected_heading = math.degrees(math.atan2(100.0, -200.0))
        if expected_heading < 0:
            expected_heading += 360.0
        self.assertAlmostEqual(res["heading"], expected_heading, places=4)

    def test_decode_airborne_velocity_subtype_3(self):
        # Test airspeed decoding (Subtype 3)
        res = decode_airborne_velocity(self.sub3_velocity_msg)
        self.assertEqual(res["icao_address"], "75804B")
        self.assertEqual(res["subtype"], 3)
        self.assertEqual(res["speed_type"], "True Airspeed")
        
        # Assert airspeed and heading values
        self.assertEqual(res["speed"], 300.0)
        self.assertEqual(res["heading"], 180.0)
        
        # Components derived from airspeed and heading:
        # Heading 180 degrees is South, so ew = 0, ns = -300
        self.assertAlmostEqual(res["east_west_velocity"], 0.0, places=4)
        self.assertAlmostEqual(res["north_south_velocity"], -300.0, places=4)

    def test_decode_airborne_velocity_errors(self):
        # Not a Type Code 19 message
        not_tc19_msg = "8D75804B580FF2CF7E9BA6F701D0"  # TC 11 message
        with self.assertRaises(ValueError):
            decode_airborne_velocity(not_tc19_msg)


if __name__ == "__main__":
    unittest.main()
