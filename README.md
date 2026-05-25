# ADS-B Decoder, Visualiser & Waveform Simulation Toolkit

A high-fidelity Python toolkit for parsing, decoding, and simulating 1090 MHz Mode S Extended Squitter (ADS-B) transmissions. This repository covers the complete ADS-B signal chain — from CRC validation and CPR position reconstruction to Pulse Position Modulation (PPM) waveform generation, IQ baseband simulation, and AWGN channel modelling.

### [**Live Visualiser Demo**](https://ads-b-signal-decoder-visualiser.vercel.app/)

![ADS-B Visualiser Dashboard](screenshot.png)

*Interactive flight telemetry and map dashboard decoding real-time transponder signals.*

---

## 1. What is ADS-B and Why It Matters

**Automatic Dependent Surveillance–Broadcast (ADS-B)** is the cornerstone of modern global air traffic management, replacing legacy Cooperative Independent Surveillance (like Primary and Secondary Surveillance Radars) under the FAA's **NextGen** and Europe's **SESAR** initiatives.

* **Automatic:** Broadcasts periodically (typically at $1 \text{ Hz}$) without needing interrogation from ground stations or other aircraft.
* **Dependent:** Relies on onboard GNSS/GPS receivers and altimeters to compute state vector parameters.
* **Surveillance:** Provides accurate position, velocity, and status data for air traffic control (ATC) and Traffic Collision Avoidance Systems (TCAS/ACAS).
* **Broadcast:** Transmits data omnidirectionally over a RF carrier frequency of $1090 \text{ MHz}$ using Pulse Position Modulation (PPM) at $1 \text{ Mbps}$.

### Why It Matters
Compared to Secondary Surveillance Radar (SSR), which relies on a rotating antenna with update rates of 4 to 12 seconds, ADS-B provides continuous, highly accurate, and low-latency state vectors. It reduces airspace separation minimums, enables automated conflict detection, and allows aircraft equipped with **ADS-B In** to maintain local situational awareness of surrounding traffic directly in the cockpit.

---

## 2. System Architecture

This toolkit covers the **complete end-to-end ADS-B signal chain** — from synthesising a physically accurate Mode S RF waveform all the way through demodulation, parsing, and interactive telemetry visualisation.

```mermaid
flowchart TD
    A(["🛩  ADS-B Hex Message\n e.g. 8D75804B580FF2CF..."])
    B["Bit Encoder\n hex_to_bits()"]
    C["PPM Waveform Generator\n generate_ppm_waveform()\n 8 µs preamble · 1 Mbit/s · 20 Msps"]
    D["IQ / Baseband Simulation\n to_iq_signal()\n I = s·cos(2πf·t) · Q = s·sin(2πf·t)"]
    E["Noise Channel — AWGN\n add_awgn_noise()\n Configurable SNR in dB"]
    F["Demodulator\n demodulate_ppm()\n Matched-filter energy decision · BER metric"]
    G["Parser — parser_adsb.py\n CRC · DF · ICAO · Type Code"]
    H["Decoder — decoder.py\n CPR Position · Altitude · Velocity"]
    I(["🗺  Visualiser — visualiser.py / index.html\n Live map · Gauges · Telemetry dashboard"])

    A --> B --> C --> D --> E --> F --> G --> H --> I

    style A fill:#0F1923,stroke:#00A8E8,color:#D4D8DD
    style B fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style C fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style D fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style E fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style F fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style G fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style H fill:#0F1923,stroke:#1E2530,color:#D4D8DD
    style I fill:#0F1923,stroke:#00A8E8,color:#D4D8DD
```

### Repository Structure

```
.
├── waveform.py          # Layers 1–5: PPM encoding, IQ, AWGN, demodulation, BER, plotting
├── parser_adsb.py       # Layer 6: Mode S packet validation and bit slicing
├── decoder.py           # Layer 7: CPR position, altitude, and velocity decoding
├── visualiser.py        # Layer 8: Local web server serving the dashboard
├── index.html           # Interactive telemetry and map dashboard (Leaflet.js)
├── api/                 # Vercel serverless functions (decode_position, decode_velocity)
├── test_waveform.py     # Unit tests — waveform layers (27 test cases)
├── test_parser.py       # Unit tests — CRC validation and packet slicing
├── test_decoder.py      # Unit tests — CPR, altitude, and velocity math
├── requirements.txt     # numpy · matplotlib · scipy
└── .gitignore
```

### A. Packet Parsing ([parser_adsb.py](parser_adsb.py))
This module extracts low-level fields from the 112-bit Extended Squitter frame:
* **Downlink Format (DF) Slicing:** Extracts bits 1-5 to identify the protocol format (typically DF 17 or DF 18).
* **ICAO Address Extraction:** Slices bits 9-32 representing the unique 24-bit aircraft transponder address.
* **Type Code (TC) Detection:** Slices bits 33-37 of the Message (ME) payload to determine the category of transponder data (e.g., Identification, Airborne Position, Airborne Velocity).
* **CRC Parity Validation:** Simulates a 24-bit feedback shift register to perform binary polynomial division (modulo-2 division). The generator polynomial used is:
  $$G(x) = x^{24} + x^{23} + x^{22} + x^{21} + x^{20} + x^{19} + x^{18} + x^{16} + x^{14} + x^{13} + x^{12} + x^{11} + x^{10} + x^3 + x^1 + 1$$
  *(Represented in hex as `0xFFF409` or `0x1FFF409` including the leading coefficient).*

### B. State Decoding ([decoder.py](decoder.py))
This module handles spatial and physical reconstruction of the telemetry:

* **Compact Position Reporting (CPR) Decoding:** Slices the 34 bits (17 bits for latitude, 17 bits for longitude) allocated in Airborne Position messages (TC 9-18).
  * **Global Decoding:** Reconstructs the absolute, globally unambiguous latitude and longitude from an **Even** (Format $F=0$) and an **Odd** (Format $F=1$) frame received within a 10-second window.
  * **Zone Transition Support ($NL$):** Implements the $NL(lat)$ function specifying the number of longitude zones at a given latitude to account for the convergence of meridians toward the poles.
* **Altitude Reconstruction:** Decodes the 12-bit altitude field. Supports:
  * **25-foot Resolution (Q-bit = 1):** Slices out the Q-bit, constructs an 11-bit integer $N$, and calculates: $\text{Altitude (ft)} = (N \times 25) - 1000$.
  * **100-foot Resolution (Q-bit = 0):** Decodes legacy 12-bit Gillham/Gray-coded transponder telemetry into altitude.
* **Airborne Velocity Decoding (TC 19):** Decodes subsonic and supersonic horizontal speed, heading, and vertical rates:
  * **Ground Speed (Subtypes 1 & 2):** Parses East-West and North-South signed vector components, returning Ground Speed ($v = \sqrt{V_{ew}^2 + V_{ns}^2}$) and Track Angle ($h = \text{atan2}(V_{ew}, V_{ns})$).
  * **Airspeed (Subtypes 3 & 4):** Extracts heading and Indicated Airspeed (IAS) or True Airspeed (TAS) directly.
  * **Vertical Rate:** Extracts climb/descent speed ($64 \text{ ft/min}$ resolution) and vertical source (Barometric vs. GNSS).

### C. Waveform Simulation ([waveform.py](waveform.py))
This module simulates the physical Mode S signal chain from bits to baseband:

* **PPM Encoding:** Generates a Mode S-compliant preamble (4 pulses at 0, 1, 3.5, 4.5 µs) and encodes each data bit as a 1 µs Manchester-style PPM symbol (0.5 µs pulse-first for `1`, pulse-second for `0`).
* **IQ Baseband Upconversion:** Multiplies the real PPM envelope by a configurable IF carrier, producing `I(t)` and `Q(t)` components for SDR compatibility analysis.
* **AWGN Channel Simulation:** Adds Additive White Gaussian Noise at a configurable SNR (dB), computed from signal power to produce statistically correct noise variance.
* **Threshold Demodulation:** Recovers bit estimates from noisy waveforms using a per-bit energy comparison between the two 0.5 µs half-periods (matched filter decision).
* **BER Analysis:** Computes the Bit Error Rate between original and decoded bit arrays across SNR levels.
* **4-Panel Waveform Plot:** Generates a professional dark-theme matplotlib figure showing:
  1. Clean PPM baseband waveform with annotated preamble region
  2. AWGN-noisy waveform overlaid with BER readout
  3. IQ (I/Q component) signal at the configured IF
  4. Power Spectral Density (FFT magnitude spectrum)

| Signal Parameter   | Value                                              |
|--------------------|----------------------------------------------------|
| Modulation         | PPM (Pulse Position Modulation)                    |
| Bit rate           | 1 Mbit/s (1 µs per bit)                           |
| Pulse width        | 0.5 µs                                             |
| Preamble           | 8 µs — pulses at 0, 1, 3.5, 4.5 µs               |
| Data length        | 56 bits (short) or 112 bits (Extended Squitter)    |
| Default sample rate| 20 Msps (20 samples per µs)                        |

---

## 3. How to Run the Toolkit

### Run the Demonstrations
Execute the main decoder module to parse sample transponder signals:
```bash
python3 decoder.py
```
This runs position and velocity calculations against verified test vectors.

To run the parser module independently on a custom hex message:
```bash
python3 parser_adsb.py 8D4840D6202CC371C32CE0576098
```

### Run the Automated Unit Test Suites
Execute the full test suite (40 tests across parser, decoder, and waveform modules):
```bash
# Run all tests together
python3 -m unittest test_parser.py test_decoder.py test_waveform.py -v

# Or run individual suites
python3 test_decoder.py      # CPR position, altitude, velocity
python3 test_parser.py       # CRC and packet slicing
python3 test_waveform.py     # PPM encoding, IQ, AWGN, demodulation
```

### Launch the Waveform Simulator
Generate a 4-panel waveform analysis plot for any hex message:
```bash
# Default test message (Cebu Pacific Air RP-C3191)
python3 waveform.py

# Custom message with noise simulation at 10 dB SNR
python3 waveform.py 8D4840D6202CC371C32CE0576098 10
```

### Launch the Visualisation Dashboard
To run the interactive web interface, navigate to the project directory and run:
```bash
python3 visualiser.py
```
Then open [http://localhost:8080](http://localhost:8080) in your web browser.

---

## 4. Verification & Example Outputs

### Web Visualiser Dashboard in Action
![ADS-B Visualiser Demo](demo.gif)

### CPR Position Decoder Output
When running position decoding on a pair of Even/Odd messages from Cebu Pacific Air flight **RP-C3191** (Airbus A319):
* **Even Message:** `8D75804B580FF2CF7E9BA6F701D0`
* **Odd Message:**  `8D75804B580FF6B283EB7A157117`

```text
Decoded Global Position:
  - ICAO Address:       0x75804B
  - Type Code:          11
  - Even Frame Position: (10.215775, 123.888819)
  - Odd Frame Position:  (10.216214, 123.889129)
  - Even Frame Altitude: 2175 ft
  - Odd Frame Altitude:  2175 ft
  - Distance Moved:      Approx. 0.049 km north-south
```

### Airborne Velocity Decoder Output (Type Code 19)
When decoding Ground Speed (Subtype 1) and Airspeed (Subtype 3) test vectors:

* **Subtype 1 Ground Speed Message:** `8D75804B99006599200000000000`
```text
Decoding Subtype 1 (Ground Speed):
  - Subtype:            1
  - Speed Type:         Ground Speed
  - Speed Magnitude:    223.61 knots
  - Heading/Track:      153.43°
  - E-W component:      100.00 knots
  - N-S component:      -200.00 knots
```

* **Subtype 3 Airspeed Message:** `8D75804B9B0600A5A00000000000`
```text
Decoding Subtype 3 (Airspeed):
  - Subtype:            3
  - Speed Type:         True Airspeed
  - Speed Magnitude:    300.00 knots
  - Heading/Track:      180.00°
  - E-W component:      0.00 knots
  - N-S component:      -300.00 knots
```

---

## 5. Future Work & SDR Roadmap

This toolkit is designed as a foundation for real-world Software Defined Radio (SDR) integration. Planned extensions include:

### Signal Reception & Hardware Integration

- **RTL-SDR / HackRF support** — pipe raw IQ samples directly from a USB SDR dongle into the demodulator pipeline
- **GNU Radio flowgraph** — export the PPM demodulation chain as a GNU Radio companion block for real-time processing
- **Real-time ADS-B capture** — replace simulated AWGN with live 1090 MHz captures for ground station experimentation

### Signal Processing Improvements

- **Frame synchronisation** — implement preamble correlation (matched filter bank) to detect message boundaries in a continuous IQ stream
- **Adaptive noise estimation** — replace fixed-threshold demodulation with an adaptive SNR estimator using a sliding noise floor estimate
- **Multipath / Doppler modelling** — extend the channel simulator with frequency offset and multipath fading models relevant to low-altitude ADS-B reception
- **Forward Error Correction experiments** — explore adding Reed-Solomon or LDPC outer codes for BER improvement below the Mode S CRC floor

### Expanded Decoding

- **DF 0 / DF 4 / DF 5 short squitter** — extend `parser_adsb.py` to handle 56-bit surveillance replies
- **MLAT (Multilateration)** — add time-difference-of-arrival positioning from multiple ground receivers
- **ADS-B Out simulation** — generate syntactically valid transponder broadcasts for avionics test-bench use

### Integration & Deployment

- **Streaming dashboard** — replace the manual hex-input interface with a live WebSocket feed from a running SDR receiver
- **REST API** — expose the full decode pipeline as a JSON endpoint (FastAPI) for integration with existing ATC displays
