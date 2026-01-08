"""City registry for sailing conditions."""
from __future__ import annotations

from .config import CHICAGO_NEARSHORE

# Registry of cities.
# type: 'marine' => try TGFTP marine_zones first (has waves), then grid fallback
#       'grid'   => NWS gridpoint only (no waves)
CITIES = {
    # Original 5
    "chicago": {
        "label": "Chicago",
        "type": "marine",
        "lat": 41.90,
        "lon": -87.60,
        "sailing": True,
        "marine_zones": CHICAGO_NEARSHORE,
    },
    "philly": {
        "label": "Philadelphia",
        "type": "grid",
        "lat": 39.9526,
        "lon": -75.1652,
        "sailing": False,
    },
    "kc": {
        "label": "Kansas City",
        "type": "grid",
        "lat": 39.0997,
        "lon": -94.5786,
        "sailing": False,
    },
    "slc": {
        "label": "Salt Lake City",
        "type": "grid",
        "lat": 40.7608,
        "lon": -111.8910,
        "sailing": False,
    },
    "nyc": {
        "label": "New York City",
        "type": "marine",
        "lat": 40.7128,
        "lon": -74.0060,
        "sailing": True,
        "marine_zones": [
            "marine/coastal/anz/anz338.txt",  # NY Harbor
            "marine/coastal/anz/anz353.txt",  # Sandy Hook to Fire Island Inlet
            "marine/coastal/anz/anz330.txt",  # LI Sound West
            "marine/coastal/anz/anz335.txt",  # LI Sound Central
        ],
    },
    # Popular sailing locations
    "miami": {
        "label": "Miami",
        "type": "marine",
        "lat": 25.7617,
        "lon": -80.1918,
        "sailing": True,
        "marine_zones": ["marine/coastal/amz/amz630.txt", "marine/coastal/amz/amz651.txt"],
    },
    "ftl": {
        "label": "Fort Lauderdale",
        "type": "marine",
        "lat": 26.1224,
        "lon": -80.1373,
        "sailing": True,
        "marine_zones": ["marine/coastal/amz/amz651.txt", "marine/coastal/amz/amz630.txt"],
    },
    "tb": {
        "label": "Tampa Bay",
        "type": "marine",
        "lat": 27.9506,
        "lon": -82.4572,
        "sailing": True,
        "marine_zones": ["marine/coastal/gmz/gmz830.txt", "marine/coastal/gmz/gmz836.txt"],
    },
    "la": {
        "label": "Los Angeles",
        "type": "marine",
        "lat": 34.0522,
        "lon": -118.2437,
        "sailing": True,
        "marine_zones": ["marine/coastal/pzz/pzz655.txt", "marine/coastal/pzz/pzz650.txt"],
    },
    "sd": {
        "label": "San Diego",
        "type": "marine",
        "lat": 32.7157,
        "lon": -117.1611,
        "sailing": True,
        "marine_zones": ["marine/coastal/pzz/pzz750.txt", "marine/coastal/pzz/pzz700.txt"],
    },
    "sf": {
        "label": "San Francisco",
        "type": "marine",
        "lat": 37.7749,
        "lon": -122.4194,
        "sailing": True,
        "marine_zones": ["marine/coastal/pzz/pzz540.txt", "marine/coastal/pzz/pzz530.txt"],
    },
    "seattle": {
        "label": "Seattle",
        "type": "marine",
        "lat": 47.6062,
        "lon": -122.3321,
        "sailing": True,
        "marine_zones": ["marine/coastal/pzz/pzz135.txt"],
    },
    "boston": {
        "label": "Boston",
        "type": "marine",
        "lat": 42.3601,
        "lon": -71.0589,
        "sailing": True,
        "marine_zones": ["marine/coastal/anz/anz230.txt", "marine/coastal/anz/anz250.txt"],
    },
    "newport": {
        "label": "Newport",
        "type": "marine",
        "lat": 41.4901,
        "lon": -71.3128,
        "sailing": True,
        "marine_zones": ["marine/coastal/anz/anz236.txt"],
    },
    "annapolis": {
        "label": "Annapolis",
        "type": "marine",
        "lat": 38.9784,
        "lon": -76.4922,
        "sailing": True,
        "marine_zones": ["marine/coastal/anz/anz531.txt", "marine/coastal/anz/anz532.txt"],
    },
    "portlandme": {
        "label": "Portland (ME)",
        "type": "marine",
        "lat": 43.6591,
        "lon": -70.2568,
        "sailing": True,
        "marine_zones": ["marine/coastal/anz/anz153.txt"],
    },
    "charleston": {
        "label": "Charleston",
        "type": "marine",
        "lat": 32.7765,
        "lon": -79.9311,
        "sailing": True,
        "marine_zones": ["marine/coastal/amz/amz330.txt", "marine/coastal/amz/amz350.txt"],
    },
    "nola": {
        "label": "New Orleans",
        "type": "marine",
        "lat": 29.9511,
        "lon": -90.0715,
        "sailing": True,
        "marine_zones": ["marine/coastal/gmz/gmz530.txt"],
    },
    "cleveland": {
        "label": "Cleveland",
        "type": "marine",
        "lat": 41.4993,
        "lon": -81.6944,
        "sailing": True,
        "marine_zones": ["marine/near_shore/le/lez145.txt", "marine/near_shore/le/lez142.txt"],
    },
    "milwaukee": {
        "label": "Milwaukee",
        "type": "marine",
        "lat": 43.0389,
        "lon": -87.9065,
        "sailing": True,
        "marine_zones": ["marine/near_shore/lm/lmz643.txt", "marine/near_shore/lm/lmz644.txt"],
    },
    # Austin: sailing=True (no marine product; waves "—")
    "atx": {
        "label": "Austin",
        "type": "grid",
        "lat": 30.2672,
        "lon": -97.7431,
        "sailing": True,
    },
    # Non-sailing extra
    "minneapolis": {
        "label": "Minneapolis",
        "type": "grid",
        "lat": 44.9778,
        "lon": -93.2650,
        "sailing": False,
    },
}
