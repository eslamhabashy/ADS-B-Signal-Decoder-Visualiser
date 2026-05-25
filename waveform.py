#!/usr/bin/env python3
"""
ADS-B Waveform Simulation Module
=================================

This module simulates the physical signal chain of a Mode S ADS-B transponder
operating at 1090 MHz. Starting from a raw hex message string, it generates:

  1. Binary PPM-encoded baseband waveforms (preamble + data bits)
  2. Baseband IQ (In-phase / Quadrature) signal representation
  3. AWGN-corrupted noisy channel waveforms
  4. Threshold-based PPM demodulation for bit recovery
  5. Multi-panel matplotlib plots for visual analysis

Mode S Physical Layer Parameters (RTCA DO-260B):
  - Carrier frequency  : 1090 MHz
  - Modulation         : Pulse Position Modulation (PPM)
  - Bit rate           : 1 Mbit/s (1 µs per bit)
  - Pulse width        : 0.5 µs
  - Preamble           : 8 µs  (pulses at 0, 1, 3.5, 4.5 µs)
  - Short message      : 56 data bits  (DF 0/4/5/11)
  - Long message       : 112 data bits (DF 17/18/19 — Extended Squitter)
  - Default sample rate: 20 Msps (20 samples per µs)

Usage:
  python3 waveform.py                        # plot default test message
  python3 waveform.py <hex_message> [snr_db] # plot custom message with noise
"""

import sys
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Default simulation sample rate in samples-per-second.
DEFAULT_SAMPLE_RATE: int = 20_000_000  # 20 Msps → 20 samples per µs

# Seconds per bit for Mode S PPM (1 Mbit/s).
BIT_DURATION_S: float = 1e-6  # 1 µs

# Seconds per half-bit (pulse width).
HALF_BIT_DURATION_S: float = 0.5e-6  # 0.5 µs

# Total preamble duration in seconds.
PREAMBLE_DURATION_S: float = 8e-6  # 8 µs

# Pulse start offsets within the 8 µs preamble (in seconds).
# Reference: RTCA DO-260B Table 2-3.
PREAMBLE_PULSE_OFFSETS_S: Tuple[float, ...] = (0.0e-6, 1.0e-6, 3.5e-6, 4.5e-6)


# ---------------------------------------------------------------------------
# Layer 1 — Bit Extraction
# ---------------------------------------------------------------------------


def hex_to_bits(hex_msg: str) -> np.ndarray:
    """
    Converts a Mode S hex string to a binary bit array (MSB-first).

    Each hex character is expanded to 4 bits. The resulting array has
    dtype=np.uint8 with values in {0, 1}.

    Args:
        hex_msg: Hexadecimal message string, with or without ``*``/``;`` wrappers.

    Returns:
        1-D NumPy array of uint8 bits, length = 4 × len(cleaned_hex).

    Raises:
        ValueError: If the string contains non-hex characters.
    """
    # Strip common SDR wrapper characters and whitespace.
    cleaned = hex_msg.strip().replace("*", "").replace(";", "").upper()
    if not all(c in "0123456789ABCDEF" for c in cleaned):
        raise ValueError(
            f"Invalid hex string: '{hex_msg}'. Only hexadecimal characters expected."
        )

    # Convert each byte to an 8-bit binary string then pack into an array.
    raw_bytes = bytes.fromhex(cleaned)
    bits = np.unpackbits(np.frombuffer(raw_bytes, dtype=np.uint8))
    return bits.astype(np.uint8)


# ---------------------------------------------------------------------------
# Layer 2 — PPM Waveform Synthesis
# ---------------------------------------------------------------------------


def generate_preamble(sample_rate: int = DEFAULT_SAMPLE_RATE) -> np.ndarray:
    """
    Generates the Mode S 8 µs preamble pulse sequence.

    The preamble consists of four 0.5 µs high pulses at fixed offsets within
    an 8 µs window:  t = 0, 1, 3.5, and 4.5 µs.

    Args:
        sample_rate: Signal sample rate in samples/second.

    Returns:
        1-D float64 NumPy array of length ``int(8e-6 * sample_rate)``,
        with amplitudes in {0.0, 1.0}.
    """
    n_preamble = int(PREAMBLE_DURATION_S * sample_rate)
    preamble = np.zeros(n_preamble, dtype=np.float64)

    pulse_width_samples = int(HALF_BIT_DURATION_S * sample_rate)

    for offset_s in PREAMBLE_PULSE_OFFSETS_S:
        start = int(offset_s * sample_rate)
        end = start + pulse_width_samples
        preamble[start:end] = 1.0

    return preamble


def _encode_bit_ppm(bit: int, samples_per_bit: int) -> np.ndarray:
    """
    Encodes a single bit using Mode S Pulse Position Modulation (PPM).

    PPM encoding rule:
      - Bit 1 → HIGH pulse (0 to 0.5 µs), then LOW (0.5 to 1 µs)
      - Bit 0 → LOW (0 to 0.5 µs), then HIGH pulse (0.5 to 1 µs)

    Args:
        bit: Integer 0 or 1.
        samples_per_bit: Total number of samples per 1 µs bit period.

    Returns:
        1-D float64 NumPy array of length ``samples_per_bit``.
    """
    symbol = np.zeros(samples_per_bit, dtype=np.float64)
    half = samples_per_bit // 2

    if bit == 1:
        # Pulse in first half
        symbol[:half] = 1.0
    else:
        # Pulse in second half
        symbol[half:] = 1.0

    return symbol


def generate_ppm_waveform(
    hex_msg: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates the complete Mode S PPM baseband waveform for a hex message.

    The waveform is composed of:
      1. An 8 µs preamble (four fixed pulses).
      2. N data bits encoded in PPM (1 µs per bit, 0.5 µs pulse width).

    Args:
        hex_msg: Raw hex string of a 56-bit (14 hex chars) or 112-bit
                 (28 hex chars) Mode S message.
        sample_rate: Simulation sample rate in samples/second.
                     Default is 20 Msps (20 samples per µs).

    Returns:
        Tuple of (time_axis, amplitude):
          - time_axis : float64 array, time in seconds for each sample.
          - amplitude : float64 array, normalised signal amplitude in [0, 1].

    Raises:
        ValueError: If message length is not 14 or 28 hex characters.
    """
    cleaned = hex_msg.strip().replace("*", "").replace(";", "").upper()
    if len(cleaned) not in (14, 28):
        raise ValueError(
            f"Expected 14 (56-bit) or 28 (112-bit) hex characters, got {len(cleaned)}."
        )

    bits = hex_to_bits(cleaned)
    samples_per_bit = int(BIT_DURATION_S * sample_rate)

    # Build waveform: preamble + data
    preamble = generate_preamble(sample_rate)
    data_section = np.concatenate(
        [_encode_bit_ppm(int(b), samples_per_bit) for b in bits]
    )

    waveform = np.concatenate([preamble, data_section])
    total_duration_s = len(waveform) / sample_rate
    time_axis = np.linspace(0.0, total_duration_s, len(waveform), endpoint=False)

    return time_axis, waveform


# ---------------------------------------------------------------------------
# Layer 3 — Baseband IQ Signal
# ---------------------------------------------------------------------------


def to_iq_signal(
    waveform: np.ndarray,
    if_frequency: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Upconverts a real-valued PPM baseband waveform to IQ (analytic) form
    at an intermediate frequency (IF).

    The real PPM pulse envelope ``s(t)`` is modulated to an IF carrier:
      - I(t) = s(t) · cos(2π · f_IF · t)
      - Q(t) = s(t) · sin(2π · f_IF · t)

    This is the standard baseband-to-IF upconversion used in SDR transmitters.
    A downstream receiver would then downconvert back to baseband using the
    known carrier phase.

    Args:
        waveform: Real-valued baseband PPM amplitude array.
        if_frequency: Intermediate frequency in Hz (e.g. 1e6 for 1 MHz IF).
        sample_rate: Sample rate in samples/second.

    Returns:
        Tuple of (I, Q) component arrays with dtype float64.
    """
    n = len(waveform)
    t = np.arange(n) / sample_rate
    carrier = 2.0 * np.pi * if_frequency * t

    i_component = waveform * np.cos(carrier)
    q_component = waveform * np.sin(carrier)

    return i_component, q_component


# ---------------------------------------------------------------------------
# Layer 4 — AWGN Noise Channel
# ---------------------------------------------------------------------------


def add_awgn_noise(
    signal: np.ndarray,
    snr_db: float,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """
    Adds Additive White Gaussian Noise (AWGN) to a signal at a specified SNR.

    Signal-to-Noise Ratio is defined as:
        SNR_dB = 10 · log10(P_signal / P_noise)

    The noise power is computed from the signal power and the desired SNR:
        σ² = P_signal / (10^(SNR_dB/10))

    Args:
        signal: Input signal array (real-valued).
        snr_db: Target signal-to-noise ratio in decibels.
                Lower values → more noise (harder channel).
        rng: Optional NumPy random Generator for reproducible results.
             If None, uses the global default RNG.

    Returns:
        Noisy signal array with dtype float64, same shape as ``signal``.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Signal power (mean squared amplitude)
    signal_power = np.mean(signal**2)

    # Required noise standard deviation for target SNR
    snr_linear = 10.0 ** (snr_db / 10.0)
    noise_power = signal_power / snr_linear
    noise_std = np.sqrt(noise_power)

    noise = rng.normal(0.0, noise_std, size=signal.shape)
    return signal + noise


# ---------------------------------------------------------------------------
# Layer 5 — PPM Demodulator
# ---------------------------------------------------------------------------


def demodulate_ppm(
    noisy_waveform: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    threshold: Optional[float] = None,
) -> np.ndarray:
    """
    Demodulates a (possibly noisy) Mode S PPM waveform, recovering bit estimates.

    Algorithm:
      1. Locate the data section by skipping the 8 µs preamble.
      2. For each 1 µs bit period, split into two 0.5 µs half-periods.
      3. Compare the mean energy in each half:
           - If energy(first_half) > energy(second_half): decoded bit = 1
           - Else: decoded bit = 0

    This is equivalent to a matched filter bank for the two PPM symbols.

    Args:
        noisy_waveform: Input PPM waveform (with or without noise).
        sample_rate: Sample rate in samples/second.
        threshold: Optional energy difference threshold for decision.
                   If None, pure maximum-energy decision is used.

    Returns:
        1-D uint8 NumPy array of decoded bit values.
    """
    samples_per_bit = int(BIT_DURATION_S * sample_rate)
    half = samples_per_bit // 2
    preamble_samples = int(PREAMBLE_DURATION_S * sample_rate)

    data_section = noisy_waveform[preamble_samples:]
    n_bits = len(data_section) // samples_per_bit
    decoded = np.zeros(n_bits, dtype=np.uint8)

    for i in range(n_bits):
        start = i * samples_per_bit
        bit_window = data_section[start : start + samples_per_bit]

        energy_first = np.mean(bit_window[:half] ** 2)
        energy_second = np.mean(bit_window[half:] ** 2)

        if threshold is None:
            decoded[i] = 1 if energy_first > energy_second else 0
        else:
            diff = energy_first - energy_second
            if diff > threshold:
                decoded[i] = 1
            elif diff < -threshold:
                decoded[i] = 0
            else:
                # Erasure — ambiguous, default to 0
                decoded[i] = 0

    return decoded


def compute_bit_error_rate(
    original_bits: np.ndarray, decoded_bits: np.ndarray
) -> float:
    """
    Computes the Bit Error Rate (BER) between original and decoded bit arrays.

    BER = (number of bit errors) / (total number of bits)

    Args:
        original_bits: Ground-truth bit array.
        decoded_bits: Demodulated bit array.

    Returns:
        Float between 0.0 (perfect) and 1.0 (all bits wrong).
    """
    n = min(len(original_bits), len(decoded_bits))
    errors = int(np.sum(original_bits[:n] != decoded_bits[:n]))
    return errors / n if n > 0 else 0.0


# ---------------------------------------------------------------------------
# Layer 6 — Plotting
# ---------------------------------------------------------------------------


def plot_waveform(
    hex_msg: str,
    snr_db: Optional[float] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    if_frequency: float = 1e6,
    show: bool = True,
) -> plt.Figure:
    """
    Generates a professional multi-panel waveform analysis figure.

    Panel layout:
      Panel 1 (top)    : Clean PPM baseband waveform with annotated preamble
                         and data regions.
      Panel 2          : Noisy waveform overlaid on clean (only if snr_db given).
      Panel 3          : IQ signal — I and Q components at ``if_frequency`` Hz.
      Panel 4 (bottom) : Power Spectral Density (FFT magnitude spectrum) of
                         the baseband signal.

    Args:
        hex_msg: Raw hex string of the Mode S message to visualise.
        snr_db: Optional SNR in dB for noise simulation. If None, noise panel
                is omitted and only 3 panels are shown.
        sample_rate: Simulation sample rate in samples/second.
        if_frequency: IF carrier for IQ upconversion in Hz. Default 1 MHz.
        show: If True, calls ``plt.show()`` to render the figure interactively.

    Returns:
        The generated matplotlib Figure object (useful for saving to file).
    """
    time_axis, waveform = generate_ppm_waveform(hex_msg, sample_rate)
    bits = hex_to_bits(hex_msg.strip().replace("*", "").replace(";", "").upper())
    i_comp, q_comp = to_iq_signal(waveform, if_frequency, sample_rate)

    # Number of panels depends on whether noise is requested
    n_panels = 4 if snr_db is not None else 3
    panel_height = 2.8

    # --- Figure setup with aerospace-style dark theme ---
    plt.rcParams.update(
        {
            "figure.facecolor": "#0A0E13",
            "axes.facecolor": "#0A0E13",
            "axes.edgecolor": "#1E2530",
            "axes.labelcolor": "#D4D8DD",
            "axes.titlecolor": "#D4D8DD",
            "xtick.color": "#6B7280",
            "ytick.color": "#6B7280",
            "grid.color": "#1E2530",
            "grid.linewidth": 0.6,
            "text.color": "#D4D8DD",
            "font.family": "monospace",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "lines.linewidth": 1.2,
        }
    )

    fig = plt.figure(
        figsize=(14, n_panels * panel_height),
        facecolor="#0A0E13",
    )
    fig.suptitle(
        f"MODE S ADS-B WAVEFORM ANALYSIS  ·  MSG: {hex_msg.upper()[:28]}",
        fontsize=11,
        fontweight="bold",
        color="#D4D8DD",
        y=0.98,
        fontfamily="monospace",
    )

    gs = gridspec.GridSpec(n_panels, 1, figure=fig, hspace=0.55, top=0.93, bottom=0.06)
    time_us = time_axis * 1e6  # convert to microseconds for readability

    # --- Panel 1: Clean PPM Baseband Waveform ---
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(time_us, waveform, color="#00A8E8", linewidth=1.0, label="PPM signal")
    ax1.set_title("BASEBAND PPM WAVEFORM  (CLEAN)", loc="left", pad=6)
    ax1.set_ylabel("Amplitude")
    ax1.set_ylim(-0.2, 1.3)
    ax1.grid(True, which="both", axis="x")
    ax1.set_xlim(0, time_us[-1])

    # Annotate preamble region
    preamble_end_us = PREAMBLE_DURATION_S * 1e6
    ax1.axvspan(0, preamble_end_us, alpha=0.08, color="#00A8E8")
    ax1.text(
        preamble_end_us / 2,
        1.18,
        "PREAMBLE\n8 µs",
        ha="center",
        va="bottom",
        fontsize=8,
        color="#00A8E8",
        fontfamily="monospace",
    )

    # Annotate data region
    ax1.axvspan(preamble_end_us, time_us[-1], alpha=0.04, color="#D4D8DD")
    data_mid = preamble_end_us + (time_us[-1] - preamble_end_us) / 2
    ax1.text(
        data_mid,
        1.18,
        f"DATA BITS  ({len(bits)} bits)",
        ha="center",
        va="bottom",
        fontsize=8,
        color="#6B7280",
        fontfamily="monospace",
    )

    # Draw 8 µs boundary line
    ax1.axvline(x=preamble_end_us, color="#1E2530", linewidth=1.0, linestyle="--")

    # Annotate first few PPM pulses
    for offset_us in [o * 1e6 for o in PREAMBLE_PULSE_OFFSETS_S]:
        ax1.axvline(
            x=offset_us,
            color="#6B7280",
            linewidth=0.6,
            linestyle=":",
            alpha=0.6,
        )
    ax1.set_xlabel("Time (µs)")

    # --- Panel 2 (conditional): Noisy Waveform ---
    panel_idx = 1
    if snr_db is not None:
        noisy = add_awgn_noise(waveform, snr_db, rng=np.random.default_rng(42))
        decoded_bits = demodulate_ppm(noisy, sample_rate)
        ber = compute_bit_error_rate(bits, decoded_bits)

        ax2 = fig.add_subplot(gs[panel_idx])
        ax2.plot(
            time_us,
            noisy,
            color="#F59E0B",
            linewidth=0.7,
            alpha=0.75,
            label=f"Noisy  SNR={snr_db:.0f} dB",
        )
        ax2.plot(
            time_us,
            waveform,
            color="#00A8E8",
            linewidth=0.9,
            alpha=0.55,
            label="Clean",
        )
        ax2.set_title(
            f"AWGN CHANNEL  ·  SNR = {snr_db:.1f} dB  ·  BER = {ber:.4f}",
            loc="left",
            pad=6,
        )
        ax2.set_ylabel("Amplitude")
        ax2.set_xlim(0, time_us[-1])
        ax2.grid(True)
        ax2.legend(
            loc="upper right",
            fontsize=8,
            framealpha=0.15,
            facecolor="#0A0E13",
            edgecolor="#1E2530",
        )
        ax2.set_xlabel("Time (µs)")
        panel_idx += 1

    # --- Panel 3: IQ Signal ---
    ax3 = fig.add_subplot(gs[panel_idx])
    ax3.plot(time_us, i_comp, color="#00A8E8", linewidth=0.8, label="I (In-phase)")
    ax3.plot(
        time_us,
        q_comp,
        color="#A78BFA",
        linewidth=0.8,
        alpha=0.8,
        label="Q (Quadrature)",
    )
    ax3.set_title(
        f"IQ BASEBAND SIGNAL  ·  IF = {if_frequency/1e6:.0f} MHz", loc="left", pad=6
    )
    ax3.set_ylabel("Amplitude")
    ax3.set_xlim(0, time_us[-1])
    ax3.grid(True)
    ax3.legend(
        loc="upper right",
        fontsize=8,
        framealpha=0.15,
        facecolor="#0A0E13",
        edgecolor="#1E2530",
    )
    ax3.set_xlabel("Time (µs)")
    panel_idx += 1

    # --- Panel 4: Power Spectral Density (FFT) ---
    ax4 = fig.add_subplot(gs[panel_idx])
    n_fft = len(waveform)
    freq_axis = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate) / 1e6  # in MHz
    spectrum = np.abs(np.fft.rfft(waveform)) ** 2
    # Normalise to dBFS
    spectrum_db = 10 * np.log10(spectrum + 1e-12) - 10 * np.log10(np.max(spectrum))

    ax4.plot(freq_axis, spectrum_db, color="#10B981", linewidth=0.9)
    ax4.fill_between(freq_axis, spectrum_db, -80, alpha=0.12, color="#10B981")
    ax4.set_title("POWER SPECTRAL DENSITY  (FFT)", loc="left", pad=6)
    ax4.set_ylabel("Power (dBFS)")
    ax4.set_xlabel("Frequency (MHz)")
    ax4.set_xlim(0, freq_axis[-1])
    ax4.set_ylim(-80, 5)
    ax4.grid(True)

    if show:
        plt.show()

    return fig


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # Default: Cebu Pacific Air RP-C3191 airborne position message
    DEFAULT_MSG = "8D75804B580FF2CF7E9BA6F701D0"

    hex_input = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MSG
    snr_input = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

    print("=" * 65)
    print("ADS-B WAVEFORM SIMULATOR")
    print("=" * 65)
    print(f"  Message     : {hex_input}")
    bits = hex_to_bits(hex_input.strip().replace("*", "").replace(";", "").upper())
    print(f"  Bit count   : {len(bits)} bits")
    print(f"  Sample rate : {DEFAULT_SAMPLE_RATE / 1e6:.0f} Msps")
    print(f"  SNR channel : {snr_input:.1f} dB AWGN")

    t, w = generate_ppm_waveform(hex_input)
    total_duration_us = t[-1] * 1e6
    print(f"  Duration    : {total_duration_us:.1f} µs total")
    print(f"  Samples     : {len(w)}")

    # Demodulate and compute BER
    rng = np.random.default_rng(42)
    noisy = add_awgn_noise(w, snr_input, rng=rng)
    decoded = demodulate_ppm(noisy)
    ber = compute_bit_error_rate(bits, decoded)
    print(
        f"  BER @ {snr_input:.0f} dB : {ber:.6f}  ({int(ber * len(bits))} bit errors)"
    )
    print("=" * 65)
    print("Launching waveform plot...")

    plot_waveform(hex_input, snr_db=snr_input)
