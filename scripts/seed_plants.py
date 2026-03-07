"""
Seed script — generate realistic dummy plant data for the AgriGPT drone database.

GPS bounds from actual drone footage (confirmed from frontend marker GPS):
  Center: lat 17.5683, lon 78.9717
  Area: ~200m × 160m ≈ 8 acres
Farm: ~8 acre mango orchard, ~10m plant spacing → ~320 plants

Run with:
  python scripts/seed_plants.py
"""

import os
import sys
import random

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus

from app.core.models import Base, Plant

# ── GPS bounds: ~8 acres centred on actual farm (200m × 160m) ───────────────
# Centre derived from drone footage marker GPS: ~17.5683, 78.9717
# 200m lat span, 160m lon span  →  1 deg lat ≈ 111,320 m; 1 deg lon ≈ 97,760 m
LAT_MIN, LAT_MAX = 17.5674, 17.5692   # 200m span
LON_MIN, LON_MAX = 78.9709, 78.9725   # 160m span

# 13m plant spacing (mature mango orchard with large canopies)
SPACING_LAT = 13 / 111_320   # degrees
SPACING_LON = 13 / 97_760    # degrees
JITTER_LAT  = 2.0 / 111_320
JITTER_LON  = 2.0 / 97_760

random.seed(42)  # Reproducible output


def build_db_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    return "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
        user=quote_plus(os.getenv("DB_USER", "postgres")),
        pw=quote_plus(os.getenv("DB_PASSWORD", "password")),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        db=os.getenv("DB_NAME", "drone_db"),
    )


def make_plant(lat: float, lon: float) -> Plant:
    return Plant(
        latitude=round(lat, 7),
        longitude=round(lon, 7),
        canopy_size=random.choices(
            ["Small", "Medium", "Large"], weights=[20, 50, 30]
        )[0],
        flowering_degree=random.choices(
            ["Low", "Medium", "High"], weights=[25, 40, 35]
        )[0],
    )


def main():
    db_url = build_db_url()
    print(f"Connecting to: {db_url[:60]}...")

    engine = create_engine(db_url)

    # Create tables if they don't exist
    Base.metadata.create_all(engine)
    print("Tables ensured.")

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Truncate existing plant data
        session.execute(text("TRUNCATE TABLE plants RESTART IDENTITY CASCADE"))
        session.commit()
        print("Existing plant data cleared.")

        # Generate grid positions
        plants = []
        lat = LAT_MIN
        while lat <= LAT_MAX:
            lon = LON_MIN
            while lon <= LON_MAX:
                jlat = lat + random.uniform(-JITTER_LAT, JITTER_LAT)
                jlon = lon + random.uniform(-JITTER_LON, JITTER_LON)
                plants.append(make_plant(jlat, jlon))
                lon += SPACING_LON
            lat += SPACING_LAT

        session.bulk_save_objects(plants)
        session.commit()
        print(f"Inserted {len(plants)} plants into the database.")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
