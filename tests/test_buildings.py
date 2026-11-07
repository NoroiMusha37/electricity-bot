import pytest

from energy_bot.loe.buildings import building_matches, building_variants, normalize_building, parse_building_names


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("171", "171"),
        (" 116а ", "116-А"),  # surrounding spaces, lowercase letter, no dash
        ("116 А", "116-А"),  # space inside
        ("116-а", "116-А"),  # dash already there
        ("116A", "116-А"),  # Latin A
        ("111/1", "111/1"),  # not "number + letter": left as is
        ("11-13", "11-13"),  # range with a dash must not be mistaken for a letter suffix
    ],
)
def test_normalize_building(typed, expected):
    assert normalize_building(typed) == expected


def test_variants_start_with_canonical_and_have_no_duplicates():
    assert building_variants("116а") == ["116-А", "116а", "116А"]
    assert building_variants("171") == ["171"]


def test_parse_building_names():
    assert parse_building_names("25, 30-А, 9-б,") == ["25", "30-А", "9-Б"]
    assert parse_building_names("") == []
    assert parse_building_names(None) == []


def test_building_matches():
    affected = parse_building_names("25, 30-А")
    assert building_matches("30а", affected)
    assert not building_matches("30", affected)
    assert building_matches("171", [])  # whole street
