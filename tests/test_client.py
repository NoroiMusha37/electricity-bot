from datetime import date, datetime

import httpx
import pytest
import respx

from energy_bot.loe.client import POWER_API, SCHEDULE_API, LoeClient, LoeError
from tests.conftest import KYIV, fixture_json


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr("energy_bot.loe.client.RETRY_DELAY_SECONDS", 0)
    loe_client = LoeClient(KYIV)
    yield loe_client
    await loe_client.aclose()


def empty_collection() -> dict:
    return {"hydra:member": []}


@respx.mock
async def test_get_schedules_skips_empty_days(client):
    respx.get(f"{SCHEDULE_API}/menus").respond(json=fixture_json("menus.json"))
    schedules = await client.get_schedules()
    assert [schedule.date for schedule in schedules] == [date(2026, 10, 17)]  # Tomorrow is empty, archive ignored
    assert schedules[0].groups["5.1"][0].label == "12:00–16:00"


@respx.mock
async def test_search_cities_parses_otg_and_ranks(client):
    route = respx.get(f"{POWER_API}/pw_cities").respond(json=fixture_json("cities.json"))
    cities = await client.search_cities("Львів")
    assert route.calls.last.request.url.params["name"] == "Львів"
    # exact match, then shorter "contains" match, then longer one
    assert [city.name for city in cities] == ["Львів", "Ульвівок", "Сороки-Львівські"]
    assert cities[0].model_dump() == {"id": 693, "name": "Львів", "otg_id": 28, "otg_name": "Львівська"}


@respx.mock
async def test_search_streets_ranks_prefix_before_substring(client):
    route = respx.get(f"{POWER_API}/pw_streets").respond(json=fixture_json("streets.json"))  # real "город" result
    names = [street.name for street in await client.search_streets(693, "город")]
    assert route.calls.last.request.url.params["city.id"] == "693"
    prefix_count = sum(name.casefold().startswith("город") for name in names)
    assert all(name.casefold().startswith("город") for name in names[:prefix_count])  # all prefixes first
    assert names[:2] == ["Городоцька", "Городницька"]  # shortest prefix matches first


@respx.mock
async def test_find_groups_tries_spellings_and_returns_loe_spelling(client):
    route = respx.get(f"{POWER_API}/pw_accounts").mock(
        side_effect=[httpx.Response(200, json=empty_collection()), httpx.Response(200, json=fixture_json("accounts.json"))]
    )
    result = await client.find_groups(693, 12564, "171а")
    assert [call.request.url.params["buildingName"] for call in route.calls] == ["171-А", "171а"]
    assert result.model_dump() == {"found": True, "groups": {"5.1"}, "building": "171"}


@respx.mock
async def test_find_groups_not_in_schedule(client):
    respx.get(f"{POWER_API}/pw_accounts").respond(
        json={"hydra:member": [{"buildingName": "5", "chergGpv": "Не входить"}]}
    )
    assert (await client.find_groups(1, 2, "5")).model_dump() == {"found": True, "groups": set(), "building": "5"}


@respx.mock
async def test_find_groups_not_found(client):
    route = respx.get(f"{POWER_API}/pw_accounts").respond(json=empty_collection())
    assert (await client.find_groups(1, 2, "5а")).model_dump() == {"found": False, "groups": set(), "building": None}
    assert route.call_count == 3  # every spelling was tried


@respx.mock
async def test_get_accidents_maps_loe_fields(client):
    payload = fixture_json("accidents.json")
    route = respx.get(f"{POWER_API}/pw_accidents").respond(json=payload)
    accidents = await client.get_accidents(783, 35266)
    assert route.calls.last.request.url.params["street.id"] == "35266"
    assert [accident.id for accident in accidents] == [record["id"] for record in payload["hydra:member"]]
    first, record = accidents[0], payload["hydra:member"][0]
    # aliases: nested city/street objects, camelCase names, ISO dates with offset
    assert (first.city_id, first.street_id) == (record["city"]["id"], record["street"]["id"])
    assert first.date_event == datetime.fromisoformat(record["dateEvent"])
    assert first.date_plan_in == datetime.fromisoformat(record["datePlanIn"])


@respx.mock
async def test_accident_naive_dates_get_local_timezone(client):
    respx.get(f"{POWER_API}/pw_accidents").respond(
        json={"hydra:member": [
            {"id": 1, "dateEvent": "2026-11-06T17:05:10", "datePlanIn": "", "buildingNames": "5, 9", "koment": None}
        ]}
    )
    [accident] = await client.get_accidents(1, 2)
    assert accident.date_event == datetime(2026, 11, 6, 17, 5, 10, tzinfo=KYIV)
    assert accident.date_plan_in is None and accident.building_names == ["5", "9"]
    assert accident.comment == ""  # null kept the record instead of dropping it


@respx.mock
async def test_malformed_records_are_skipped_not_fatal(client, caplog):
    good = {"id": 7, "dateEvent": "2026-11-06T17:05:10+02:00", "buildingNames": ""}
    bad = [
        {"id": 1},  # no dateEvent
        {"id": 2, "dateEvent": "not a date"},
        {"dateEvent": "2026-11-06T17:05:10+02:00"},  # no id
        "not an object",
    ]
    respx.get(f"{POWER_API}/pw_accidents").respond(json={"hydra:member": [*bad, good]})
    accidents = await client.get_accidents(1, 2)
    assert [accident.id for accident in accidents] == [7]
    assert accidents[0].building_names == []  # empty buildingNames = whole street
    assert caplog.text.count("Skipping malformed LOE accident record") == 4
    assert "dateEvent: Field required" in caplog.text


@respx.mock
async def test_one_retry_after_network_error(client):
    route = respx.get(f"{POWER_API}/pw_streets").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json=empty_collection())]
    )
    assert await client.search_streets(1, "x") == []
    assert route.call_count == 2


@respx.mock
async def test_gives_up_after_one_retry(client):
    route = respx.get(f"{POWER_API}/pw_streets").respond(503)
    with pytest.raises(LoeError, match="failed twice"):
        await client.search_streets(1, "x")
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404),  # client error: not retried
        httpx.Response(200, text="<html>maintenance</html>"),  # not JSON
        httpx.Response(200, json=[1, 2, 3]),  # JSON, but not an object
        httpx.Response(200, json={"items": []}),  # object without hydra:member
    ],
)
async def test_bad_responses_raise_without_retry(client, response):
    route = respx.get(f"{POWER_API}/pw_streets").mock(return_value=response)
    with pytest.raises(LoeError):
        await client.search_streets(1, "x")
    assert route.call_count == 1
