import json
import os
import random
import sys
from collections import defaultdict
from typing import TypedDict

from slack import auth_test, get_profile, post_message, update_message


class User(TypedDict):
    discipline: str
    initiative: str
    display_name: str


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def format_user_ids_by_attribute(
    attribute: str, all_users: dict[str, User]
) -> dict[str, set[str]]:
    """ """
    user_ids_by_attribute = defaultdict(set)
    for user_id, user in all_users.items():
        user_ids_by_attribute[user[attribute]].add(user_id)
    return user_ids_by_attribute


def get_unmatched_user_ids_with_different_attribute(
    current_user_attribute: str,
    user_ids_by_attribute: dict[str, set[str]],
    already_matched: set[str],
) -> set[str]:
    """
    Returns user ids with a different attribute value that is not an empty string
    """
    return {
        user_id
        for discipline, user_ids in user_ids_by_attribute.items()
        if discipline != current_user_attribute and discipline != ""
        for user_id in user_ids
        if user_id not in already_matched
    }


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------
def shuffle_users_prioritizing_info(all_users: dict[str, User]) -> list[str]:
    """
    Generates a random order to start matching users. Prioritizes users with discipline or initiative information for earlier matching.
    """
    all_user_ids = [user_id for user_id, _ in all_users.items()]
    user_ids_with_info = [
        user_id
        for user_id, user in all_users.items()
        if user["discipline"] != "" or user["initiative"]
    ]
    user_ids_without_info = list(set(all_user_ids) - set(user_ids_with_info))

    random.shuffle(user_ids_with_info)
    random.shuffle(user_ids_without_info)
    return user_ids_with_info + user_ids_without_info


def generate_matches(
    all_users: dict[str, User],
) -> list[tuple[str, str]]:
    """
    Matches users into pairs by a different discipline, or by a different initiative if not, or anyone available if not.
    Returns list of tuple user_id matches. If there is an odd number of users, returns the odd person out as a pair with themself.
    """
    users_by_discipline = format_user_ids_by_attribute("discipline", all_users)
    users_by_initiative = format_user_ids_by_attribute("initiative", all_users)

    shuffled_users = shuffle_users_prioritizing_info(all_users)

    already_matched = set()
    matches = []

    for current_user_id in shuffled_users:
        if current_user_id not in already_matched:
            discipline_user_pool = get_unmatched_user_ids_with_different_attribute(
                all_users[current_user_id]["discipline"],
                users_by_discipline,
                already_matched,
            )
            initiative_user_pool = get_unmatched_user_ids_with_different_attribute(
                all_users[current_user_id]["initiative"],
                users_by_initiative,
                already_matched,
            )

            match = None
            if len(discipline_user_pool) > 0:
                match = random.choice(list(discipline_user_pool))
            elif len(initiative_user_pool) > 0:
                match = random.choice(list(initiative_user_pool))
            else:
                just_pick_someone = list(
                    set(shuffled_users) - already_matched - {current_user_id}
                )
                if len(just_pick_someone) > 0:
                    match = random.choice(just_pick_someone)
                else:
                    match = current_user_id
            already_matched.add(current_user_id)
            already_matched.add(match)
            matches.append((current_user_id, match))
    return matches


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def format_user(user: User) -> str:
    return f'{user["display_name"]} ({user["discipline"]}, {user["initiative"]})'


def cmd_pair_people():
    """Pair people by different disciplines and initiatives."""
    # token = os.environ["TOKEN"]

    users_discipline_initiative_map = json.loads(
        os.environ["USERS_DISCIPLINE_INITIATIVE_MAP"]
    )

    matches = generate_matches(users_discipline_initiative_map)

    for user1, user2 in matches:
        print(
            format_user(users_discipline_initiative_map[user1]),
            "with",
            format_user(users_discipline_initiative_map[user2]),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    commands = {
        "pair-people": cmd_pair_people,
    }
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in commands:
        print(
            f"Unknown command: {command!r}. Available: {', '.join(commands)}",
            file=sys.stderr,
        )
        sys.exit(1)
    commands[command]()


if __name__ == "__main__":
    main()
