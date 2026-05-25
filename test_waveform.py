#!/usr/bin/env python3
"""
Unit Tests for ADS-B Waveform Simulation Module (waveform.py)
=============================================================

Test coverage:
  - Layer 1: hex_to_bits  — bit extraction correctness and length
  - Layer 2: PPM encoding — preamble shape, total waveform length, bit encoding
  - Layer 3: IQ signal    — amplitude relationship to source waveform
  - Layer 4: AWGN channel — noise energy at specified SNR
  - Layer 5: Demodulator  — BER = 0 on clean signal, BER rises with noise
"""

import unittest
import numpy as np

from waveform import (
    DEFAULT_SAMPLE_RATE,
    PREAMBLE_DURATION_S,
    BIT_DURATION_S,
    hex_to_bits,
    generate_preamble,
    generate_ppm_waveform,
    to_iq_signal,
    add_awgn_noise,
    demodulate_ppm,
    compute_bit_error_rate,
)


class TestHexToBits(unittest.TestCase):
    """Tests for Layer 1 — Bit extraction."""

    def test_length_14_hex(self):
        """14 hex characters → 56 bits (short Mode S message)."""
        bits = hex_to_bits("8D4840D6202CC3")
        self.assertEqual(len(bits), 56)

    def test_length_28_hex(self):
        """28 hex characters → 112 bits (Extended Squitter)."""
        bits = hex_to_bits("8D75804B580FF2CF7E9BA6F701D0")
        self.assertEqual(len(bits), 112)

    def test_known_byte_value(self):
        """0x8D = 0b10001101 → bits [1,0,0,0,1,1,0,1]."""
        bits = hex_to_bits("8D" + "0" * 26)
        expected_first_byte = [1, 0, 0, 0, 1, 1, 0, 1]
        np.testing.assert_array_equal(bits[:8], expected_first_byte)

    def test_invalid_hex_raises(self):
        """Non-hex characters should raise ValueError."""
        with self.assertRaises(ValueError):
            hex_to_bits("8D75804BXYZWVUTS1234567890AB")

    def test_all_zeros(self):
        """All-zero message should produce all-zero bits."""
        bits = hex_to_bits("00" * 14)
        self.assertTrue(np.all(bits == 0))

    def test_all_ff(self):
        """All-0xFF message should produce all-one bits."""
        bits = hex_to_bits("FF" * 14)
        self.assertTrue(np.all(bits == 1))

    def test_sdr_wrapper_stripped(self):
        """SDR wrapper characters *...; should be silently removed."""
        bits_clean = hex_to_bits("8D4840D6202CC371C32CE0576098")
        bits_wrapped = hex_to_bits("*8D4840D6202CC371C32CE0576098;")
        np.testing.assert_array_equal(bits_clean, bits_wrapped)


class TestPreamble(unittest.TestCase):
    """Tests for the Mode S preamble generator."""

    def test_preamble_length(self):
        """Preamble must be exactly 8 µs × sample_rate samples."""
        for sr in (10_000_000, 20_000_000):
            preamble = generate_preamble(sr)
            expected = int(PREAMBLE_DURATION_S * sr)
            self.assertEqual(
                len(preamble), expected, msg=f"Preamble length at {sr} sps"
            )

    def test_preamble_amplitudes_binary(self):
        """All preamble samples must be exactly 0.0 or 1.0."""
        preamble = generate_preamble(DEFAULT_SAMPLE_RATE)
        self.assertTrue(
            np.all((preamble == 0.0) | (preamble == 1.0)),
            "Preamble contains non-binary amplitude values.",
        )

    def test_preamble_has_four_pulses(self):
        """
        Preamble must contain exactly 4 pulses.

        The first pulse starts at t=0 (sample index 0), so there is no
        preceding zero to create a rising edge via np.diff. We therefore
        count rising edges from sample 1 onwards and add 1 if sample[0]==1.
        """
        preamble = generate_preamble(DEFAULT_SAMPLE_RATE)
        # Rising edges from index 1 onward (transitions 0 → 1)
        rising_edges = int(np.sum(np.diff(preamble.astype(int)) == 1))
        # Account for the implicit rising edge at sample 0 if it starts HIGH
        if preamble[0] == 1.0:
            rising_edges += 1
        self.assertEqual(rising_edges, 4, "Expected exactly 4 preamble pulses.")

    def test_preamble_pulse_positions(self):
        """Pulses must start at t = 0, 1, 3.5, 4.5 µs."""
        sr = DEFAULT_SAMPLE_RATE
        preamble = generate_preamble(sr)
        expected_starts_samples = [
            int(0.0e-6 * sr),
            int(1.0e-6 * sr),
            int(3.5e-6 * sr),
            int(4.5e-6 * sr),
        ]
        for i, start in enumerate(expected_starts_samples):
            self.assertEqual(
                preamble[start],
                1.0,
                msg=f"Pulse {i+1} not HIGH at sample {start}",
            )


class TestPPMWaveform(unittest.TestCase):
    """Tests for Layer 2 — Full PPM waveform generation."""

    def test_waveform_length_112_bit(self):
        """
        Total waveform for 112-bit message =
        (8 µs preamble + 112 µs data) × sample_rate.
        """
        sr = DEFAULT_SAMPLE_RATE
        _, waveform = generate_ppm_waveform("8D75804B580FF2CF7E9BA6F701D0", sr)
        expected_samples = int((PREAMBLE_DURATION_S + 112 * BIT_DURATION_S) * sr)
        self.assertEqual(len(waveform), expected_samples)

    def test_waveform_length_56_bit(self):
        """56-bit message → 8 µs preamble + 56 µs data."""
        sr = DEFAULT_SAMPLE_RATE
        _, waveform = generate_ppm_waveform("8D4840D6202CC3" + "0" * 0, sr)
        # 14-char hex = 56 bits
        expected_samples = int((PREAMBLE_DURATION_S + 56 * BIT_DURATION_S) * sr)
        self.assertEqual(len(waveform), expected_samples)

    def test_time_axis_starts_at_zero(self):
        """Time axis must start at t=0."""
        t, _ = generate_ppm_waveform("8D75804B580FF2CF7E9BA6F701D0")
        self.assertAlmostEqual(t[0], 0.0, places=12)

    def test_time_axis_end_matches_duration(self):
        """Time axis endpoint should match (preamble + data) duration."""
        sr = DEFAULT_SAMPLE_RATE
        t, w = generate_ppm_waveform("8D75804B580FF2CF7E9BA6F701D0", sr)
        expected_end = (PREAMBLE_DURATION_S + 112 * BIT_DURATION_S) - 1.0 / sr
        self.assertAlmostEqual(t[-1], expected_end, places=9)

    def test_waveform_amplitudes_binary(self):
        """All waveform samples must be in {0.0, 1.0} for a clean signal."""
        _, waveform = generate_ppm_waveform("8D75804B580FF2CF7E9BA6F701D0")
        self.assertTrue(np.all((waveform == 0.0) | (waveform == 1.0)))

    def test_invalid_message_length_raises(self):
        """Messages that are not 14 or 28 hex chars must raise ValueError."""
        with self.assertRaises(ValueError):
            generate_ppm_waveform("8D4840D6")  # Too short (8 chars)

    def test_bit_one_pulse_in_first_half(self):
        """
        A bit value of 1 must produce a HIGH pulse in the first half of
        the bit period and LOW in the second half.
        """
        sr = DEFAULT_SAMPLE_RATE
        samples_per_bit = int(BIT_DURATION_S * sr)
        half = samples_per_bit // 2
        preamble_samples = int(PREAMBLE_DURATION_S * sr)

        # 0xFF = 0b11111111 → first 8 data bits are all 1s
        _, waveform = generate_ppm_waveform("FF" * 14, sr)
        data = waveform[preamble_samples:]

        first_bit = data[:samples_per_bit]
        self.assertTrue(
            np.all(first_bit[:half] == 1.0), "First half should be HIGH for bit=1"
        )
        self.assertTrue(
            np.all(first_bit[half:] == 0.0), "Second half should be LOW for bit=1"
        )

    def test_bit_zero_pulse_in_second_half(self):
        """
        A bit value of 0 must produce LOW in the first half and a HIGH
        pulse in the second half.
        """
        sr = DEFAULT_SAMPLE_RATE
        samples_per_bit = int(BIT_DURATION_S * sr)
        half = samples_per_bit // 2
        preamble_samples = int(PREAMBLE_DURATION_S * sr)

        # 0x00 → first 8 data bits are all 0s
        _, waveform = generate_ppm_waveform("00" * 14, sr)
        data = waveform[preamble_samples:]

        first_bit = data[:samples_per_bit]
        self.assertTrue(
            np.all(first_bit[:half] == 0.0), "First half should be LOW for bit=0"
        )
        self.assertTrue(
            np.all(first_bit[half:] == 1.0), "Second half should be HIGH for bit=0"
        )


class TestIQSignal(unittest.TestCase):
    """Tests for Layer 3 — IQ baseband upconversion."""

    def setUp(self):
        _, self.waveform = generate_ppm_waveform("8D75804B580FF2CF7E9BA6F701D0")

    def test_iq_lengths_match_waveform(self):
        """I and Q must have the same length as the input waveform."""
        i, q = to_iq_signal(self.waveform, if_frequency=1e6)
        self.assertEqual(len(i), len(self.waveform))
        self.assertEqual(len(q), len(self.waveform))

    def test_iq_envelope_matches_waveform(self):
        """
        sqrt(I² + Q²) must equal the original waveform amplitude at
        every sample (within floating-point tolerance).
        """
        i, q = to_iq_signal(self.waveform, if_frequency=1e6)
        envelope = np.sqrt(i**2 + q**2)
        np.testing.assert_allclose(envelope, self.waveform, atol=1e-10)

    def test_iq_zero_where_waveform_zero(self):
        """Where the PPM waveform is 0.0, both I and Q must be 0.0."""
        i, q = to_iq_signal(self.waveform, if_frequency=1e6)
        zero_mask = self.waveform == 0.0
        np.testing.assert_array_equal(i[zero_mask], 0.0)
        np.testing.assert_array_equal(q[zero_mask], 0.0)


class TestAWGNChannel(unittest.TestCase):
    """Tests for Layer 4 — AWGN noise channel."""

    def setUp(self):
        _, self.waveform = generate_ppm_waveform("8D75804B580FF2CF7E9BA6F701D0")
        self.rng = np.random.default_rng(seed=0)

    def test_noisy_signal_different_from_clean(self):
        """Noisy signal must not be identical to clean signal."""
        noisy = add_awgn_noise(self.waveform, snr_db=10.0, rng=self.rng)
        self.assertFalse(np.allclose(noisy, self.waveform))

    def test_output_length_unchanged(self):
        """AWGN must not change the length of the signal."""
        noisy = add_awgn_noise(self.waveform, snr_db=10.0, rng=self.rng)
        self.assertEqual(len(noisy), len(self.waveform))

    def test_high_snr_close_to_original(self):
        """At very high SNR (60 dB), noisy signal should be very close to clean."""
        noisy = add_awgn_noise(self.waveform, snr_db=60.0, rng=self.rng)
        np.testing.assert_allclose(noisy, self.waveform, atol=1e-2)

    def test_snr_is_approximately_correct(self):
        """
        Measured SNR of the noisy output should be close to the specified SNR.
        Allow ±3 dB tolerance due to finite-length estimation variance.
        """
        target_snr_db = 15.0
        noisy = add_awgn_noise(self.waveform, snr_db=target_snr_db, rng=self.rng)
        noise = noisy - self.waveform
        signal_power = np.mean(self.waveform**2)
        noise_power = np.mean(noise**2)
        measured_snr_db = 10 * np.log10(signal_power / (noise_power + 1e-20))
        self.assertAlmostEqual(measured_snr_db, target_snr_db, delta=3.0)


class TestDemodulator(unittest.TestCase):
    """Tests for Layer 5 — PPM demodulation and BER."""

    def setUp(self):
        self.hex_msg = "8D75804B580FF2CF7E9BA6F701D0"
        self.bits = hex_to_bits(self.hex_msg)
        _, self.waveform = generate_ppm_waveform(self.hex_msg)

    def test_demodulation_zero_noise(self):
        """Demodulating a clean waveform must recover bits with BER = 0."""
        decoded = demodulate_ppm(self.waveform)
        ber = compute_bit_error_rate(self.bits, decoded)
        self.assertEqual(ber, 0.0, "BER must be exactly 0 for zero-noise demodulation.")

    def test_decoded_length_matches_original(self):
        """Decoder must return same number of bits as the original message."""
        decoded = demodulate_ppm(self.waveform)
        self.assertEqual(len(decoded), len(self.bits))

    def test_high_snr_low_ber(self):
        """At high SNR (20 dB), BER should remain very low (< 0.01)."""
        rng = np.random.default_rng(42)
        noisy = add_awgn_noise(self.waveform, snr_db=20.0, rng=rng)
        decoded = demodulate_ppm(noisy)
        ber = compute_bit_error_rate(self.bits, decoded)
        self.assertLess(ber, 0.01, f"High-SNR BER too high: {ber:.4f}")

    def test_low_snr_higher_ber(self):
        """At very low SNR (0 dB), BER should be measurably above 0."""
        rng = np.random.default_rng(42)
        noisy = add_awgn_noise(self.waveform, snr_db=0.0, rng=rng)
        decoded = demodulate_ppm(noisy)
        ber = compute_bit_error_rate(self.bits, decoded)
        # BER at 0 dB SNR should be noticeably above zero
        self.assertGreater(ber, 0.0, "Expected some bit errors at 0 dB SNR.")

    def test_ber_range_valid(self):
        """BER must always be between 0.0 and 1.0 inclusive."""
        rng = np.random.default_rng(99)
        noisy = add_awgn_noise(self.waveform, snr_db=5.0, rng=rng)
        decoded = demodulate_ppm(noisy)
        ber = compute_bit_error_rate(self.bits, decoded)
        self.assertGreaterEqual(ber, 0.0)
        self.assertLessEqual(ber, 1.0)

    def test_compute_ber_all_wrong(self):
        """Complemented bits should yield BER = 1.0."""
        inverted = 1 - self.bits
        ber = compute_bit_error_rate(self.bits, inverted)
        self.assertAlmostEqual(ber, 1.0)

    def test_compute_ber_all_correct(self):
        """Identical arrays should yield BER = 0.0."""
        ber = compute_bit_error_rate(self.bits, self.bits.copy())
        self.assertEqual(ber, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
