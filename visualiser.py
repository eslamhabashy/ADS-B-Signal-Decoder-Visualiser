#!/usr/bin/env python3
"""
ADS-B Signal Decoder Visualiser

This script starts a local web server (http://localhost:8080) and opens a browser
to display an interactive flight instrumentation and map dashboard. It connects
directly to the decoding functions in decoder.py.
"""

import http.server
import socketserver
import json
import webbrowser
import threading
import sys
import os
from typing import Dict, Any

# Ensure we can import decoder and parser from local path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from decoder import decode_airborne_position, decode_airborne_velocity

PORT = 8080

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ADS-B Signal Decoder & Visualiser</title>
    
    <!-- Google Fonts & Leaflet CSS -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Space+Grotesk:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
    
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: rgba(20, 26, 46, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-cyan: #38bdf8;
            --accent-green: #10b981;
            --accent-rose: #f43f5e;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        header {
            background-color: rgba(11, 15, 25, 0.9);
            border-bottom: 1px solid var(--border-color);
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(10px);
            z-index: 100;
        }

        header h1 {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 1px;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        header .status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: var(--text-muted);
        }

        header .indicator {
            width: 8px;
            height: 8px;
            background-color: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--accent-green);
        }

        .main-container {
            display: flex;
            flex: 1;
            height: calc(100vh - 60px);
            overflow: hidden;
        }

        /* Sidebar Control Panel */
        .sidebar {
            width: 420px;
            background-color: rgba(15, 23, 42, 0.8);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 25px;
            gap: 25px;
            overflow-y: auto;
            backdrop-filter: blur(15px);
            z-index: 90;
        }

        .section-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 15px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--accent-cyan);
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Tabs */
        .tabs {
            display: flex;
            background-color: rgba(0, 0, 0, 0.3);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        .tab-btn {
            flex: 1;
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 8px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .tab-btn.active {
            background-color: var(--panel-bg);
            color: var(--text-main);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .tab-content {
            display: none;
            flex-direction: column;
            gap: 15px;
        }

        .tab-content.active {
            display: flex;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .form-group label {
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
        }

        .form-group input {
            background-color: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--border-color);
            padding: 10px 12px;
            border-radius: 6px;
            color: var(--text-main);
            font-family: 'Space Grotesk', sans-serif;
            font-size: 14px;
            letter-spacing: 0.5px;
            transition: border-color 0.3s;
        }

        .form-group input:focus {
            outline: none;
            border-color: var(--accent-cyan);
        }

        .btn-decode {
            background: linear-gradient(90deg, #0284c7, #4f46e5);
            border: none;
            color: white;
            padding: 12px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.1s;
            margin-top: 5px;
        }

        .btn-decode:hover {
            opacity: 0.9;
        }

        .btn-decode:active {
            transform: scale(0.98);
        }

        /* Flight Stats Panel */
        .stats-panel {
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            backdrop-filter: blur(10px);
        }

        .stat-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            padding-bottom: 8px;
        }

        .stat-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .stat-label {
            font-size: 13px;
            color: var(--text-muted);
        }

        .stat-val {
            font-size: 15px;
            font-weight: 700;
            font-family: 'Space Grotesk', sans-serif;
        }

        .stat-val.accent {
            color: var(--accent-cyan);
        }

        /* Map and Instruments Section */
        .workspace {
            flex: 1;
            display: flex;
            flex-direction: column;
            position: relative;
        }

        #map {
            flex: 1;
            background-color: #070913;
        }

        /* HUD Instruments Layer */
        .hud-layer {
            position: absolute;
            bottom: 30px;
            left: 30px;
            right: 30px;
            height: 220px;
            display: flex;
            gap: 25px;
            pointer-events: none;
            z-index: 80;
        }

        .instrument {
            flex: 1;
            background: rgba(11, 15, 25, 0.85);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 15px;
            backdrop-filter: blur(12px);
            pointer-events: auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: relative;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }

        .instrument-title {
            position: absolute;
            top: 10px;
            left: 15px;
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .instrument canvas {
            margin-top: 10px;
        }

        .digital-readout {
            position: absolute;
            bottom: 12px;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 16px;
            font-weight: 700;
            color: var(--accent-cyan);
        }
    </style>
</head>
<body>

    <header>
        <h1>ADS-B SIGNAL DECODER & VISUALISER</h1>
        <div class="status">
            <div class="indicator"></div>
            <span>Decoder Engine Active (Port 8080)</span>
        </div>
    </header>

    <div class="main-container">
        <!-- Control Panel Sidebar -->
        <div class="sidebar">
            <div>
                <div class="section-title">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>
                    Telemetry Input
                </div>
                <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 15px;">
                    Paste hex packets directly from an SDR feed.
                </p>
                
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('position-tab')">Position (CPR)</button>
                    <button class="tab-btn" onclick="switchTab('velocity-tab')">Velocity (TC19)</button>
                </div>
            </div>

            <!-- Position Tab -->
            <div id="position-tab" class="tab-content active">
                <div class="form-group">
                    <label for="even-msg">Even Message (F=0)</label>
                    <input type="text" id="even-msg" value="8D75804B580FF2CF7E9BA6F701D0" placeholder="e.g. 8D75804B580FF2C...">
                </div>
                <div class="form-group">
                    <label for="odd-msg">Odd Message (F=1)</label>
                    <input type="text" id="odd-msg" value="8D75804B580FF6B283EB7A157117" placeholder="e.g. 8D75804B580FF6B...">
                </div>
                <button class="btn-decode" onclick="decodePosition()">Decode Position</button>
            </div>

            <!-- Velocity Tab -->
            <div id="velocity-tab" class="tab-content">
                <div class="form-group">
                    <label for="vel-msg">Velocity Hex Message</label>
                    <input type="text" id="vel-msg" value="8D75804B99006599200000000000" placeholder="e.g. 8D75804B990065...">
                </div>
                <button class="btn-decode" onclick="decodeVelocity()">Decode Velocity</button>
            </div>

            <!-- Stats/Telemetry Display Panel -->
            <div class="stats-panel">
                <div class="section-title" style="margin-bottom: 0;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"></path><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path></svg>
                    Decoded State Vector
                </div>
                
                <div class="stat-row">
                    <span class="stat-label">ICAO Address</span>
                    <span class="stat-val accent" id="val-icao">N/A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Position Lat/Lon</span>
                    <span class="stat-val" id="val-pos">N/A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Baro Altitude</span>
                    <span class="stat-val" id="val-alt">N/A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Horizontal Speed</span>
                    <span class="stat-val" id="val-speed">N/A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Track / Heading</span>
                    <span class="stat-val" id="val-heading">N/A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Vertical Speed</span>
                    <span class="stat-val" id="val-vs">N/A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">GNSS/Baro Diff</span>
                    <span class="stat-val" id="val-diff">N/A</span>
                </div>
            </div>
        </div>

        <!-- Interactive Map & Avionics Hud -->
        <div class="workspace">
            <div id="map"></div>
            
            <div class="hud-layer">
                <!-- Instrument 1: Compass / Track Indicator -->
                <div class="instrument">
                    <span class="instrument-title">Compass / Heading</span>
                    <canvas id="compassCanvas" width="140" height="140"></canvas>
                    <div class="digital-readout" id="compassReadout">---°</div>
                </div>
                
                <!-- Instrument 2: Altimeter -->
                <div class="instrument">
                    <span class="instrument-title">Altitude Tape</span>
                    <canvas id="altimeterCanvas" width="100" height="140"></canvas>
                    <div class="digital-readout" id="altReadout">----- FT</div>
                </div>
                
                <!-- Instrument 3: Airspeed Indicator -->
                <div class="instrument">
                    <span class="instrument-title">Airspeed Indicator</span>
                    <canvas id="airspeedCanvas" width="140" height="140"></canvas>
                    <div class="digital-readout" id="speedReadout">--- KT</div>
                </div>
                
                <!-- Instrument 4: VSI (Vertical Speed Indicator) -->
                <div class="instrument">
                    <span class="instrument-title">Vertical Speed</span>
                    <canvas id="vsiCanvas" width="100" height="140"></canvas>
                    <div class="digital-readout" id="vsReadout">---- FPM</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Leaflet JS & App Script -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    <script>
        // Initialize Map
        const map = L.map('map', {
            zoomControl: false
        }).setView([10.216, 123.889], 12);
        
        // Add CartoDB Dark Matter tile layer for premium dark-mode aesthetic
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
        }).addTo(map);
        
        L.control.zoom({ position: 'topright' }).addTo(map);

        let evenMarker = null;
        let oddMarker = null;
        let pathLine = null;

        // Custom aircraft icon rotating dynamically
        const aircraftIcon = L.divIcon({
            html: `<svg id="plane-svg" style="transform: rotate(0deg); transition: transform 0.8s ease;" width="30" height="30" viewBox="0 0 24 24" fill="#38bdf8"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L14 19v-5.5L21 16z"/></svg>`,
            className: 'aircraft-div-icon',
            iconSize: [30, 30],
            iconAnchor: [15, 15]
        });

        // Initialize Gauges
        let currentHeading = 0;
        let currentAltitude = 0;
        let currentSpeed = 0;
        let currentVS = 0;

        function drawCompass(heading) {
            const canvas = document.getElementById('compassCanvas');
            const ctx = canvas.getContext('2d');
            const cx = canvas.width / 2;
            const cy = canvas.height / 2;
            const radius = 55;

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Draw outer dial ring
            ctx.beginPath();
            ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 3;
            ctx.stroke();

            // Draw card ticks rotated
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(-heading * Math.PI / 180);

            // Ticks every 30 deg
            for (let angle = 0; angle < 360; angle += 10) {
                ctx.beginPath();
                if (angle % 30 === 0) {
                    ctx.moveTo(0, -radius);
                    ctx.lineTo(0, -radius + 8);
                    ctx.strokeStyle = '#38bdf8';
                    ctx.lineWidth = 1.5;
                    
                    // Labels N, E, S, W
                    ctx.save();
                    ctx.translate(0, -radius + 18);
                    ctx.rotate(-angle * Math.PI / 180); // Rotate back so text is upright
                    ctx.fillStyle = '#94a3b8';
                    ctx.font = 'bold 9px Space Grotesk';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    let label = angle;
                    if (angle === 0) label = 'N';
                    if (angle === 90) label = 'E';
                    if (angle === 180) label = 'S';
                    if (angle === 270) label = 'W';
                    ctx.fillText(label, 0, 0);
                    ctx.restore();
                } else {
                    ctx.moveTo(0, -radius);
                    ctx.lineTo(0, -radius + 4);
                    ctx.strokeStyle = '#475569';
                    ctx.lineWidth = 1;
                }
                ctx.stroke();
                ctx.rotate(10 * Math.PI / 180);
            }
            ctx.restore();

            // Draw stationary center airplane icon pointing Up
            ctx.save();
            ctx.translate(cx, cy);
            ctx.fillStyle = '#f8fafc';
            ctx.beginPath();
            ctx.moveTo(0, -15);
            ctx.lineTo(12, 5);
            ctx.lineTo(3, 3);
            ctx.lineTo(2, 10);
            ctx.lineTo(6, 13);
            ctx.lineTo(-6, 13);
            ctx.lineTo(-2, 10);
            ctx.lineTo(-3, 3);
            ctx.lineTo(-12, 5);
            ctx.closePath();
            ctx.fill();
            ctx.restore();
        }

        function drawAltimeter(alt) {
            const canvas = document.getElementById('altimeterCanvas');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Draw center pointer box
            ctx.fillStyle = '#1e293b';
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.rect(5, 55, 90, 30);
            ctx.fill();
            ctx.stroke();

            // Draw moving tape scale
            const step = 20; // scale tick spacing
            const scaleFactor = 0.1; // pixels per foot
            ctx.fillStyle = '#94a3b8';
            ctx.strokeStyle = '#475569';
            ctx.textAlign = 'right';
            ctx.font = '10px Space Grotesk';

            for (let i = -3; i <= 3; i++) {
                // Find nearest altitude step
                let val = Math.round(alt / 100) * 100 + (i * 100);
                if (val < 0) continue;
                
                let y = 70 - (val - alt) * scaleFactor;
                if (y < 10 || y > 130) continue;

                ctx.beginPath();
                ctx.moveTo(50, y);
                ctx.lineTo(60, y);
                ctx.stroke();
                ctx.fillText(val, 45, y + 3);
            }
        }

        function drawSpeedometer(speed) {
            const canvas = document.getElementById('airspeedCanvas');
            const ctx = canvas.getContext('2d');
            const cx = canvas.width / 2;
            const cy = canvas.height / 2;
            const radius = 55;

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Outer dial ring
            ctx.beginPath();
            ctx.arc(cx, cy, radius, 0.75 * Math.PI, 2.25 * Math.PI);
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 3;
            ctx.stroke();

            // Tick Marks
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(0.75 * Math.PI);
            const maxSpeed = 400; // max gauge speed
            const angleRange = 1.5 * Math.PI;

            for (let val = 0; val <= maxSpeed; val += 20) {
                let angle = (val / maxSpeed) * angleRange;
                ctx.save();
                ctx.rotate(angle);
                ctx.beginPath();
                ctx.moveTo(0, -radius);
                ctx.lineTo(0, -radius + (val % 100 === 0 ? 8 : 4));
                ctx.strokeStyle = val % 100 === 0 ? '#38bdf8' : '#475569';
                ctx.lineWidth = val % 100 === 0 ? 1.5 : 1;
                ctx.stroke();
                
                if (val % 100 === 0) {
                    ctx.save();
                    ctx.translate(0, -radius + 18);
                    ctx.rotate(-angle - 0.75 * Math.PI); // keep text straight
                    ctx.fillStyle = '#94a3b8';
                    ctx.font = '8px Space Grotesk';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(val, 0, 0);
                    ctx.restore();
                }
                ctx.restore();
            }
            ctx.restore();

            // Draw Pointer Needle
            let targetAngle = 0.75 * Math.PI + (Math.min(speed, maxSpeed) / maxSpeed) * angleRange;
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(targetAngle);
            ctx.strokeStyle = '#ef4444';
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.moveTo(0, 0);
            ctx.lineTo(0, -radius + 6);
            ctx.stroke();
            
            // Needle center pin
            ctx.beginPath();
            ctx.arc(0, 0, 5, 0, 2 * Math.PI);
            ctx.fillStyle = '#ef4444';
            ctx.fill();
            ctx.restore();
        }

        function drawVSI(vs) {
            const canvas = document.getElementById('vsiCanvas');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Draw vertical scale line
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(50, 10);
            ctx.lineTo(50, 130);
            ctx.stroke();

            // Center indicator
            ctx.fillStyle = '#1e293b';
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(50, 70);
            ctx.lineTo(75, 60);
            ctx.lineTo(75, 80);
            ctx.closePath();
            ctx.fill();
            ctx.stroke();

            // Draw VS needle offset
            ctx.strokeStyle = vs >= 0 ? '#10b981' : '#f43f5e';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(50, 70);
            
            // Scale: 70 is zero. Maximum +- 4000 FPM corresponding to +-50px
            let offset = (vs / 4000.0) * 50;
            // clamp offset
            offset = Math.max(-50, Math.min(50, offset));
            ctx.lineTo(50, 70 - offset);
            ctx.stroke();

            // Ticks
            ctx.fillStyle = '#94a3b8';
            ctx.font = '9px Space Grotesk';
            ctx.textAlign = 'left';
            ctx.fillText('+2K', 60, 45);
            ctx.fillText('0', 60, 73);
            ctx.fillText('-2K', 60, 100);
        }

        // Run gauge rendering loop
        function updateGauges() {
            drawCompass(currentHeading);
            drawAltimeter(currentAltitude);
            drawSpeedometer(currentSpeed);
            drawVSI(currentVS);
        }

        // Initialize Gauges at 0
        updateGauges();

        // Switch telemtry tab
        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            const activeBtn = event.target;
            activeBtn.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }

        // API Call: Decode position
        function decodePosition() {
            const evenMsg = document.getElementById('even-msg').value;
            const oddMsg = document.getElementById('odd-msg').value;

            fetch('/api/decode_position', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ even_msg: evenMsg, odd_msg: oddMsg })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert('Decoding Error: ' + data.error);
                    return;
                }

                // Update metrics display
                document.getElementById('val-icao').innerText = '0x' + data.icao_address;
                document.getElementById('val-pos').innerText = `${data.latitude_even.toFixed(5)}, ${data.longitude_even.toFixed(5)}`;
                document.getElementById('val-alt').innerText = (data.altitude_even !== null ? data.altitude_even + ' ft' : 'N/A');
                
                // Update gauge values
                currentAltitude = data.altitude_even || 0;
                updateGauges();
                
                document.getElementById('altReadout').innerText = currentAltitude + ' FT';

                // Plot on Leaflet map
                const posEven = [data.latitude_even, data.longitude_even];
                const posOdd = [data.latitude_odd, data.longitude_odd];

                if (evenMarker) map.removeLayer(evenMarker);
                if (oddMarker) map.removeLayer(oddMarker);
                if (pathLine) map.removeLayer(pathLine);

                evenMarker = L.marker(posEven, { icon: aircraftIcon }).addTo(map)
                    .bindPopup(`<b>Even Frame</b><br>ICAO: 0x${data.icao_address}<br>Alt: ${data.altitude_even} ft`).openPopup();
                
                oddMarker = L.marker(posOdd).addTo(map)
                    .bindPopup(`<b>Odd Frame</b><br>Alt: ${data.altitude_odd} ft`);

                pathLine = L.polyline([posEven, posOdd], {
                    color: '#38bdf8',
                    weight: 3,
                    dashArray: '5, 10',
                    opacity: 0.8
                }).addTo(map);

                // Re-center map to Even frame position
                map.setView(posEven, 13);
            })
            .catch(err => alert('Network/Server error: ' + err));
        }

        // API Call: Decode velocity
        function decodeVelocity() {
            const velMsg = document.getElementById('vel-msg').value;

            fetch('/api/decode_velocity', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hex_msg: velMsg })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert('Decoding Error: ' + data.error);
                    return;
                }

                // Update text readout
                document.getElementById('val-icao').innerText = '0x' + data.icao_address;
                document.getElementById('val-speed').innerText = `${data.speed.toFixed(1)} kt (${data.speed_type})`;
                document.getElementById('val-heading').innerText = (data.heading !== null ? data.heading.toFixed(1) + '°' : 'N/A');
                document.getElementById('val-vs').innerText = (data.vertical_rate !== null ? data.vertical_rate + ' ft/min' : 'N/A');
                document.getElementById('val-diff').innerText = (data.altitude_difference !== null ? data.altitude_difference + ' ft' : 'N/A');

                // Update gauge values
                currentHeading = data.heading || 0;
                currentSpeed = data.speed || 0;
                currentVS = data.vertical_rate || 0;
                updateGauges();

                // Rotate Compass and Speed readouts
                document.getElementById('compassReadout').innerText = Math.round(currentHeading) + '°';
                document.getElementById('speedReadout').innerText = Math.round(currentSpeed) + ' KT';
                document.getElementById('vsReadout').innerText = currentVS + ' FPM';

                // Rotate the plane icon on the map if marker exists
                const planeSvg = document.getElementById('plane-svg');
                if (planeSvg) {
                    planeSvg.style.transform = `rotate(${currentHeading}deg)`;
                }
            })
            .catch(err => alert('Network/Server error: ' + err));
        }
    </script>
</body>
</html>
"""


class ADSBVisualiserHTTPHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format: str, *args: Any) -> None:
        # Override to suppress console spam from HTTP requests
        pass

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        
        try:
            params = json.loads(post_data.decode("utf-8"))
        except Exception:
            self.send_error_response("Invalid JSON data.")
            return

        if self.path == "/api/decode_position":
            self.handle_decode_position(params)
        elif self.path == "/api/decode_velocity":
            self.handle_decode_velocity(params)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_decode_position(self, params: Dict[str, Any]) -> None:
        even_msg = params.get("even_msg", "")
        odd_msg = params.get("odd_msg", "")
        
        if not even_msg or not odd_msg:
            self.send_error_response("Both Even and Odd messages are required.")
            return
            
        try:
            res = decode_airborne_position(even_msg, odd_msg)
            self.send_success_response(res)
        except Exception as e:
            self.send_error_response(str(e))

    def handle_decode_velocity(self, params: Dict[str, Any]) -> None:
        hex_msg = params.get("hex_msg", "")
        
        if not hex_msg:
            self.send_error_response("Velocity hex message is required.")
            return
            
        try:
            res = decode_airborne_velocity(hex_msg)
            self.send_success_response(res)
        except Exception as e:
            self.send_error_response(str(e))

    def send_success_response(self, data: Dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_response(self, error_msg: str) -> None:
        self.send_response(200)  # Standard response with error payload
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error_msg}).encode("utf-8"))


def start_server() -> None:
    # Use socketserver to avoid port conflict issues
    handler = ADSBVisualiserHTTPHandler
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print("-" * 65)
        print(f"ADS-B Visualiser Server launched on: http://localhost:{PORT}")
        print("Press Ctrl+C to terminate.")
        print("-" * 65)
        
        # Open default browser automatically
        webbrowser.open(f"http://localhost:{PORT}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.shutdown()


if __name__ == "__main__":
    start_server()
