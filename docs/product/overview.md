# Ukladen Product Overview

Status: product vision. The business functionality described below is not implemented.
Only the project foundation currently exists.

## 1. Purpose

The system is designed to organize the academic and personal workflow of a BSUIR student inside a single workspace.

The primary user interface is a flexible calendar connected to:

- university schedule;
- tasks;
- deadlines;
- subjects;
- notes;
- study materials;
- reminders;
- AI assistant.

---

## 2. Primary User Flow

The user:

1. registers;
2. selects a university group;
3. optionally selects a subgroup;
4. the system retrieves schedule data;
5. the schedule appears in the personal calendar;
6. the user adapts the calendar to personal needs;
7. the user creates personal events;
8. the user creates tasks and deadlines;
9. the user adds notes and materials;
10. the user uses AI for search, analysis and workspace actions.

---

## 3. Personal Calendar

The calendar is the central product module.

The user should be able to:

- view day;
- view week;
- view month;
- create personal events;
- edit personal events;
- delete personal events;
- drag and drop events;
- resize events;
- filter the calendar;
- interact with imported university lessons.

---

## 4. BSUIR Schedule Integration

The BSUIR schedule is an external source of academic events.

An imported lesson must not become an immutable personal constraint.

The user may:

- attend the lesson;
- mark it as skipped;
- hide it;
- add a personal description;
- link a task;
- link a note;
- link materials;
- free the time interval for personal planning.

Original external schedule data and user-specific changes must remain logically separated.

---

## 5. Subject Workspace

Each subject acts as a separate workspace context.

Example:

```text
Knowledge Base Design
|
|-- upcoming classes
|-- tasks
|-- deadlines
|-- notes
|-- materials
`-- related events
```

---

## 6. Tasks

A task may contain:

- title;
- description;
- subject;
- status;
- priority;
- deadline;
- estimated duration;
- dependencies;
- related materials;
- related notes;
- related calendar blocks.

A task may be split into multiple time blocks.

---

## 7. Free Time Calculation

The system should be able to calculate the user's free time.

The calculation should consider:

- attended university classes;
- personal calendar events;
- scheduled task blocks;
- user schedule overrides.

If a lesson is marked as skipped, it should not automatically occupy time in the personal plan.

---

## 8. Notes

A user can create notes and link them to:

- subject;
- task;
- university lesson;
- calendar event;
- material;
- another note.

---

## 9. Materials

Supported material sources may include:

- documents;
- PDF files;
- links;
- text materials;
- other supported educational files.

Files must be stored in object storage.

The system should be able to extract text from supported materials for search and RAG.

---

## 10. Relations Between Objects

The workspace should support flexible Notion-like relations.

Examples:

```text
Task -> Material
Task -> Note
Subject -> Material
Subject -> Note
ScheduleEvent -> Task
CalendarEvent -> Note
Note -> Note
```

---

## 11. Search

The system should provide two search layers.

### Structured Search

Search by:

- title;
- subject;
- type;
- date;
- status;
- explicit fields.

### Semantic Search

Search over notes and materials using embeddings + pgvector.

---

## 12. AI Assistant

The AI assistant is an interface to workspace data and actions.

Example user requests:

```text
What do I have tomorrow?
```

```text
When do I have two free hours?
```

```text
Find materials for my second Knowledge Base Design lab.
```

```text
When should I work on this lab?
```

```text
Schedule gym tomorrow at 18:00.
```

The AI assistant must not execute SQL directly.

It must work through approved application tools.

---

## 13. AI Tool Calling

Example:

```text
User
 |
 v
AI
 |
 +--> get_calendar
 +--> get_tasks
 +--> get_free_slots
 +--> search_materials
 +--> create_task
 `--> propose_calendar_event
```

Business logic remains inside normal application services.

---

## 14. Reminders

The system should support:

- task reminders;
- deadline reminders;
- calendar event reminders.

Initial channel:

```text
in-app
```

Possible future channels:

```text
email
Telegram
push notifications
```

---

## 15. Future Development

The project should be suitable for future growth.

Possible directions:

- Google Calendar integration;
- additional universities;
- Telegram integration;
- mobile application;
- shared workspaces;
- collaborative notes;
- intelligent planning;
- additional AI providers;
- separate AI Service when justified;
- separate Notification Service when justified.

The initial implementation remains a modular monolith.
