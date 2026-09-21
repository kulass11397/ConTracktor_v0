# ConTracktor v1.7.5 — weekly grid in clean Payroll interface

The v1.7.4 weekly attendance grid was present in the core Payroll page but hidden by the clean-interface toolbar. In v1.7.5, Payroll > Attendance Actions > Batch attendance (weekly grid) opens the Saturday–Friday project-tabbed grid. The previous single-day batch-entry form is removed from the visible workflow, and old action callers route to the grid.

The grid retains company-wide employees, project tabs, non-overlapping split-site shifts, saved drafts, finalized absences, and automatic closing of affected project days for Weekly Payroll. Site-kiosk attendance and Edit attendance / pay remain available for correcting recorded logs. Existing expense reports, 15% management-fee billing option, and all financial records are unchanged.

Verification: 161 regression checks passed, including a real clean-interface menu smoke test and confirmation that Batch attendance routes to the grid. The standard installer was tested on an isolated copy of the client database and includes no client records.

Security status: unsigned prerelease. A local Defender scan cannot guarantee acceptance on the client's computer. Do not bypass a warning if one appears; submit the flagged installer for Microsoft review instead.
