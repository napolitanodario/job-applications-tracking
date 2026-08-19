# Job applications tracking

Automatic tool for job application tracking using LLMs and mailbox integration.

## Current snapshot

`applications.csv` is generated from Gmail **Updates** (category:updates). Latest refresh: **2026-08-19**.

It tracks:

- applications already sent (LinkedIn Easy Apply, company ATS, job boards)
- companies that replied, with the outcome when available

Job alerts (LinkedIn `jobalerts-noreply`), OTP/login codes, and incomplete drafts (for example GenieAI) are excluded.

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

### Snapshot counts (2026-08-19)

- **35** applications in the file (34 from the August 2026 search + 1 older PwC intern outcome)
- **1** in screening / take-home (Bending Spoons)
- **12** received / under review
- **16** sent, no company reply yet
- **6** rejected
