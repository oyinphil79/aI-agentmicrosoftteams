# Permissions matrix

See [identity.md](identity.md) for the full identity design. Quick reference:

| Capability | Agent | Data access path | Permission |
|---|---|---|---|
| Policy Q&A | knowledge | Azure AI Search / Foundry IQ | Search Index Data Reader (MI) + `allowed_groups` filter from user token |
| "What did I miss" | knowledge | Work IQ | Delegated, user's token |
| Create ticket | it | MCP `contoso-itsm` | Entra-authenticated MCP endpoint; requester = token subject; **user approval** |
| Ticket status | it | MCP `contoso-itsm` | Own tickets only |
| Leave balance | hr | HR REST API | Delegated, own record only |
| Manager | hr | Graph `/me/manager` | `User.ReadBasic.All` (delegated) |
| Meetings | hr | Graph `/me/calendarView` | `Calendars.Read` (delegated) |
| Email reply | outlook flow | Graph `/me/sendMail` | `Mail.Send` (delegated) |
