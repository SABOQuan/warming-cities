"""The ten locked cities for this project, per ROADMAP.md — shared by every download script
(air quality, temperature, and eventually sea level) so the list only lives in one place.
"""

from __future__ import annotations

# city -> (lat, lon). Locked list, per ROADMAP.md.
CITIES: dict[str, tuple[float, float]] = {
    "lahore": (31.5497, 74.3436),
    "beijing": (39.9042, 116.4074),
    "sao_paulo": (-23.5505, -46.6333),
    "cairo": (30.0444, 31.2357),
    "new_york": (40.7128, -74.0060),
    "delhi": (28.7041, 77.1025),
    "manila": (14.5995, 120.9842),
    "jakarta": (-6.2088, 106.8456),
    "london": (51.5074, -0.1278),
    "sydney": (-33.8688, 151.2093),
}
