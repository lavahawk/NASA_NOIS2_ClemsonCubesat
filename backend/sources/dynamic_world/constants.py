from __future__ import annotations

from datetime import date

DATASET_ID = "GOOGLE/DYNAMICWORLD/V1"
LOWER_BOUND_DATE = date(2015, 6, 27)

class DynamicWorldLabel:
    WATER = "water"
    TREES = "trees"
    GRASS = "grass"
    FLOODED_VEGETATION = "flooded_vegetation"
    CROPS = "crops"
    SHRUB_AND_SCRUB = "shrub_and_scrub"
    BUILT = "built"
    BARE = "bare"
    SNOW_AND_ICE = "snow_and_ice"

    BY_INDEX = {
        0: WATER,
        1: TREES,
        2: GRASS,
        3: FLOODED_VEGETATION,
        4: CROPS,
        5: SHRUB_AND_SCRUB,
        6: BUILT,
        7: BARE,
        8: SNOW_AND_ICE,
    }

    @classmethod
    def all(cls) -> list[str]:
        return list(cls.BY_INDEX.values())


PROBABILITY_BANDS = DynamicWorldLabel.all()
