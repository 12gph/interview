"""Seed catalog.

Loaded on every process start so a fresh clone is usable immediately -- the brief
makes this a hard requirement rather than a nicety.

The stock figures are chosen, not arbitrary:

* ``TEE-SGE-M`` has exactly one unit, which makes "two requests racing for the
  final unit" reproducible by hand from the UI as well as from the test suite.
* ``TEE-SND-S`` has zero units: the out-of-stock SKU.
* ``black / l`` and ``sage / s`` have no SKU at all: the unavailable combinations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedOptionValue:
    value: str
    label: str
    swatch: str | None = None


@dataclass(frozen=True)
class SeedDimension:
    key: str
    label: str
    values: tuple[SeedOptionValue, ...]


@dataclass(frozen=True)
class SeedSku:
    id: str
    options: dict[str, str]
    price_minor: int
    stock: int
    image_url: str


@dataclass(frozen=True)
class SeedProduct:
    id: str
    name: str
    description: str
    currency: str
    hero_image_url: str
    dimensions: tuple[SeedDimension, ...]
    skus: tuple[SeedSku, ...]


COLOURS = SeedDimension(
    key="colour",
    label="Colour",
    values=(
        SeedOptionValue("black", "Black", "#1C1C1E"),
        SeedOptionValue("sand", "Sand", "#D8C3A5"),
        SeedOptionValue("sage", "Sage", "#8A9A7B"),
    ),
)

SIZES = SeedDimension(
    key="size",
    label="Size",
    values=(
        SeedOptionValue("s", "S"),
        SeedOptionValue("m", "M"),
        SeedOptionValue("l", "L"),
    ),
)

SEED_PRODUCT = SeedProduct(
    id="aurora-tee",
    name="Aurora Classic Tee",
    description=(
        "Midweight organic cotton tee with a relaxed shoulder and a straight hem. "
        "Garment-dyed and pre-shrunk, made to be worn on repeat."
    ),
    currency="USD",
    hero_image_url="/images/aurora-tee-hero.svg",
    dimensions=(COLOURS, SIZES),
    skus=(
        # 9 theoretical combinations (3 colours x 3 sizes), 7 real SKUs.
        #
        # black / l  -> deliberately absent  (unavailable combination #1)
        # sage  / s  -> deliberately absent  (unavailable combination #2)
        SeedSku("TEE-BLK-S", {"colour": "black", "size": "s"}, 4900, 4, "/images/tee-black-s.svg"),
        SeedSku("TEE-BLK-M", {"colour": "black", "size": "m"}, 4900, 2, "/images/tee-black-m.svg"),
        SeedSku("TEE-SND-S", {"colour": "sand", "size": "s"}, 5300, 0, "/images/tee-sand-s.svg"),
        SeedSku("TEE-SND-M", {"colour": "sand", "size": "m"}, 5300, 6, "/images/tee-sand-m.svg"),
        SeedSku("TEE-SND-L", {"colour": "sand", "size": "l"}, 5300, 3, "/images/tee-sand-l.svg"),
        SeedSku("TEE-SGE-M", {"colour": "sage", "size": "m"}, 5700, 1, "/images/tee-sage-m.svg"),
        SeedSku("TEE-SGE-L", {"colour": "sage", "size": "l"}, 5700, 5, "/images/tee-sage-l.svg"),
    ),
)
