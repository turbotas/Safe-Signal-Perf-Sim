# Safe Signal Performance Simulator - Agent Context

## Related Server Code

The backend server software is located at `../Server/` (sibling to this repository).

Key documentation:
- `../Server/Documentation/API Overview.md` - Full API reference
- `../Server/Documentation/Mobile Language Sync Contract.md` - Victim smartphone app language contract
- `../Server/Documentation/I18N and Master Data Lifecycle.md` - How i18n and languages work in the system

## Language Endpoints (Important Distinction)

The server maintains **two distinct language concepts**:

1. **Interface languages** (`GET /api/languages?for_interface=true`)  
   Used by the **case management web application** (staff/admin UI). These are languages the management interface can display in.

2. **Case languages** (`GET /api/languages?for_case=true`)  
   Used by the **victim smartphone app** (the device the victim carries). These are the languages the mobile app supports.  
   *When creating a case in the simulator, we represent a victim, so we must pick from this set.*

## Gender Endpoint

`GET /api/master/genders` returns the available gender values used by case forms and validation.

## When Updating Simulator Data

- Always fetch genders from `/api/master/genders`
- Always fetch the victim's language from `/api/languages?for_case=true` (NOT `for_interface=true`)
- Never modify any code under `../Server/`
