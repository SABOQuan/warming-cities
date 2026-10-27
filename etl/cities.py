"""The eleven locked cities for this project, per ROADMAP.md — shared by every download script
(air quality and temperature) so the list only lives in one place.

Ho Chi Minh City replaced Manila and Addis Ababa replaced Cairo, and Santiago was added: OpenAQ
only has PM2.5 for Manila and Cairo from 2023, too short to show a trend. Addis Ababa and Santiago
have monitors running 2016 to the present; Ho Chi Minh City's single US Diplomatic Post monitor
covers 2016-2024. All three have long GHCN temperature records with a solid 1961-1990 baseline.
"""

from __future__ import annotations

# city -> (lat, lon). Locked list, per ROADMAP.md.
CITIES: dict[str, tuple[float, float]] = {
    "lahore": (31.5497, 74.3436),
    "beijing": (39.9042, 116.4074),
    "sao_paulo": (-23.5505, -46.6333),
    "addis_ababa": (9.0300, 38.7400),
    "new_york": (40.7128, -74.0060),
    "delhi": (28.7041, 77.1025),
    "ho_chi_minh_city": (10.8231, 106.6297),
    "jakarta": (-6.2088, 106.8456),
    "london": (51.5074, -0.1278),
    "sydney": (-33.8688, 151.2093),
    "santiago": (-33.4489, -70.6693),
}
