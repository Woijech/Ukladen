# Ukladen Product Overview

This file is a navigation entry, not a second product specification.

Ukladen combines a freely organized page workspace and personal calendar with an
AI assistant and BSUIR IIS integration. Academic subjects never impose the user's
organization: standalone pages and events work without a subject or collection.

- [Product overview](docs/product/overview.md): goals, scope and current status.
- [Workspace requirements](docs/product/workspace.md): scenarios and acceptance rules.
- [Open decisions](docs/product/open-questions.md): unresolved scope and proposed defaults.
- [Implementation roadmap](docs/development/implementation-roadmap.md): backend slices.
- [System architecture](SYSTEM_ARCHITECTURE.md): primary architecture contract.
- [Documentation index](docs/README.md): specifications and implementation guides.

Status: the complete target product is not implemented. Existing backend calendar,
authentication, profiles and public IIS integration are described in the linked
implementation guides. Nested pages with typed blocks, page/calendar links,
collections/tags and saved calendar views are implemented, backend only;
Database/property/record APIs, table/calendar views and nonblocking date projections
with mixed calendar display are implemented. AI and authenticated IIS remain not implemented.
One-shot calendar reminders and the durable in-app inbox are implemented, backend only;
see [reminder contracts](docs/development/reminders.md).
