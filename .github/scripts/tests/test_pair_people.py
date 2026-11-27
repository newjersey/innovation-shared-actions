from pair_people import (
    format_user_ids_by_attribute,
    User,
    generate_matches,
    get_unmatched_user_ids_with_different_attribute,
    shuffle_users_prioritizing_info,
)

import pytest


def test_format_user_ids_by_attribute():
    all_users: dict[str, User] = {
        "user_eng_bizx": {
            "discipline": "Engineering",
            "initiative": "Business Experience",
            "display_name": "BizX Engineer",
        },
        "user_eng_resx": {
            "discipline": "Engineering",
            "initiative": "Resident Experience",
            "display_name": "ResX Engineer",
        },
        "user_design_resx": {
            "discipline": "Design",
            "initiative": "Business Experience",
            "display_name": "BizX Designer",
        },
    }

    expected_by_discipline = {
        "Engineering": {"user_eng_bizx", "user_eng_resx"},
        "Design": {"user_design_resx"},
    }
    assert (
        format_user_ids_by_attribute("discipline", all_users) == expected_by_discipline
    )

    expected_by_initiative = {
        "Business Experience": {"user_design_resx", "user_eng_bizx"},
        "Resident Experience": {"user_eng_resx"},
    }
    assert (
        format_user_ids_by_attribute("initiative", all_users) == expected_by_initiative
    )


@pytest.mark.parametrize(
    "user_ids_by_discipline,already_matched",
    [
        (
            {
                "Engineering": {"user_eng_bizx", "user_eng_resx"},
                "Design": {"expected_match"},
            },
            set(),
        ),
        (
            {
                "Engineering": {"user_eng_bizx", "user_eng_resx"},
                "Design": {"has_alread_been_matched", "expected_match"},
            },
            {"has_alread_been_matched"},
        ),
    ],
)
def test_get_unmatched_user_ids_with_different_attribute(
    user_ids_by_discipline, already_matched
):
    assert get_unmatched_user_ids_with_different_attribute(
        "Engineering", user_ids_by_discipline, already_matched
    ) == {"expected_match"}


def test_shuffle_users_prioritizing_info():
    all_users: dict[str, User] = {
        "has_discipline_info": {
            "discipline": "Engineering",
            "initiative": "",
            "display_name": "Engineer Person",
        },
        "has_initiative_info": {
            "discipline": "",
            "initiative": "Resident Experience",
            "display_name": "ResX Person",
        },
        "no_discipline_or_initiative_info": {
            "discipline": "",
            "initiative": "",
            "display_name": "No Info",
        },
    }
    info_prioritized_users = shuffle_users_prioritizing_info(all_users)
    assert set(info_prioritized_users) == all_users.keys()
    assert info_prioritized_users[-1] == "no_discipline_or_initiative_info"
    # Doesn't test the shuffle


def test_generate_matches():
    all_users_different_disciplines: dict[str, User] = {
        "engineer_1": {
            "discipline": "Engineering",
            "initiative": "Resident Experience",
            "display_name": "Engineer 1",
        },
        "engineer_2": {
            "discipline": "Engineering",
            "initiative": "Resident Experience",
            "display_name": "Engineer 2",
        },
        "designer_1": {
            "discipline": "Design",
            "initiative": "",
            "display_name": "Designer 1",
        },
        "no_info_1": {
            "discipline": "",
            "initiative": "",
            "display_name": "No Info",
        },
        "no_info_2": {
            "discipline": "",
            "initiative": "",
            "display_name": "No Info",
        },
    }
    matches = generate_matches(all_users_different_disciplines)
    assert len(matches) == 3

    designer_engineer_match = next(
        match
        for match in matches
        if (match[0].startswith("designer") or match[1].startswith("designer"))
        and (match[0].startswith("engineer") or match[1].startswith("engineer"))
    )
    person_1, person_2 = designer_engineer_match
    assert person_1.startswith("engineer") or person_2.startswith("engineer")

    no_info_engineer_match = next(
        match
        for match in matches
        if (match[0].startswith("no_info") or match[1].startswith("no_info"))
        and (match[0].startswith("engineer") or match[1].startswith("engineer"))
    )
    person_1, person_2 = no_info_engineer_match
    assert person_1.startswith("engineer") or person_2.startswith("engineer")

    no_info_self_match = next(
        match
        for match in matches
        if match[0].startswith("no_info") and match[1].startswith("no_info")
    )
    person_1, person_2 = no_info_self_match
    assert person_1 == person_2
