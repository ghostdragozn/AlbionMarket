from decimal import Decimal

TAX_RATE = Decimal("0.1005")
ZERO_MONEY = Decimal("0.00")

CITY_NAMES = [
    "Fort Sterling",
    "Thetford",
    "Martlock",
    "Bridgewatch",
    "Lymhurst",
]

ITEM_CATEGORIES = ["ORE", "LOG", "BAR", "PLANK"]
TIERS = list(range(1, 9))


def build_item_code(category: str, tier: int) -> str:
    return f"{category}-{roman_tier(tier)}"


def build_seed_items() -> list[dict[str, str | int]]:
    items: list[dict[str, str | int]] = []
    for category in ITEM_CATEGORIES:
        for tier in TIERS:
            items.append(
                {
                    "code": build_item_code(category, tier),
                    "category": category,
                    "tier": tier,
                    "display_name": build_item_code(category, tier),
                }
            )
    return items


def roman_tier(value: int) -> str:
    numerals = {
        1: "I",
        2: "II",
        3: "III",
        4: "IV",
        5: "V",
        6: "VI",
        7: "VII",
        8: "VIII",
    }
    return numerals[value]
