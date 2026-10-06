from app.modules.academics.domain.profile import AcademicProfile, AcademicProfileConflict
from app.modules.schedule.application.provider import Lesson, Schedule, ScheduleProvider
from app.modules.schedule.domain.selection import matches_subgroup


class AcademicProfileRequired(Exception):
    pass


def select_subgroup(schedule: Schedule, subgroup: int | None) -> Schedule:
    def select(lessons: list[Lesson]) -> list[Lesson]:
        return [lesson for lesson in lessons if matches_subgroup(lesson.subgroup, subgroup)]

    def select_days(days: dict[str, list[Lesson]] | None) -> dict[str, list[Lesson]] | None:
        return {day: select(lessons) for day, lessons in days.items()} if days is not None else None

    return schedule.model_copy(
        update={
            "schedules": select_days(schedule.schedules),
            "next_schedules": select_days(schedule.next_schedules),
            "exams": select(schedule.exams) if schedule.exams is not None else None,
        }
    )


class ScheduleService:
    def __init__(self, provider: ScheduleProvider) -> None:
        self.provider = provider

    def for_group(self, group_number: str, subgroup: int | None = None) -> Schedule | None:
        schedule = self.provider.get_group_schedule(group_number)
        return select_subgroup(schedule, subgroup) if schedule is not None else None

    def for_profile(self, profile: AcademicProfile | None) -> Schedule | None:
        if profile is None:
            raise AcademicProfileRequired()
        schedule = self.provider.get_group_schedule(profile.group.name)
        if schedule is None:
            return None
        if schedule.group is None or schedule.group.id != profile.group.id:
            raise AcademicProfileConflict()
        return select_subgroup(schedule, profile.subgroup)
