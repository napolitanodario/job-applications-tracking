# Job applications tracking

Automatic tool for job application tracking using LLMs and mailbox integration.

## Current snapshot

`applications.csv` is generated from Gmail **Updates** (`category:updates`). Latest refresh: **2026-08-20 08:18 UTC**.

It tracks:

- applications already sent (LinkedIn Easy Apply, company ATS, job boards)
- companies that replied, with the outcome when available

Job alerts (LinkedIn `jobalerts-noreply` / `jobs-noreply` "similar jobs" / "apply now"), Amazon University Talent subscriptions, OTP/login codes, and incomplete drafts are excluded.

This hourly run found **no new application or outcome emails** after 2026-08-18 (Bending Spoons screening/task invite). Newest mail in Updates today was Amazon delivery tracking.

### CSV columns

| Column | Meaning |
| --- | --- |
| `azienda` | Company or recruiting agency |
| `ruolo` | Job title |
| `sede` | Location when present in the email |
| `canale` | How the application was sent (LinkedIn, Ashby, Lever, Workday, ...) |
| `data_candidatura` | Date the application was submitted |
| `stato` | `Candidatura inviata` / `Ricevuta / in revisione` / `Screening / task` / `Rifiutata` |
| `azienda_ha_risposto` | `si` if the company/ATS sent a status email beyond LinkedIn "application sent" |
| `esito` | Outcome or latest signal |
| `data_ultimo_aggiornamento` | Date of the latest relevant email |
| `note` | Extra context |

### Snapshot counts (2026-08-20)

- **35** applications in the file (34 from the August 2026 search + 1 older PwC intern outcome)
- **1** in screening / take-home (Bending Spoons)
- **12** received / under review
- **16** sent, no company reply yet
- **6** rejected
