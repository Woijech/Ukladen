def matches_subgroup(lesson_subgroup: int, selected_subgroup: int | None) -> bool:
    return selected_subgroup is None or lesson_subgroup in (0, selected_subgroup)
