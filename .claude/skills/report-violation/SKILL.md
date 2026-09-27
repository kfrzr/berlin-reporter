---
name: report-violation
description: Report a car, van, motorcycle, moped or e-scooter that is illegally parked or driving illegally in Berlin to the responsible authority, from a photo plus a short description. Use when the user shares a photo of a vehicle violating traffic/parking rules (bike lane, sidewalk, double parking, crossing, red light, ...) and wants it reported, or says "report this", "anzeigen", "Falschparker".
---

# Report a traffic violation in Berlin

Uses the `berlin-reporter` MCP server. Goal: one photo + one sentence from the user → a correct,
complete report in front of them within a minute, submitted on their "yes".

## 1. Get the photo
- If the user gave a path, use it. If they said "the latest"/"my last photo", call
  `list_inbox_photos` and take the newest (they sync phone photos into `~/berlin-reports/inbox`).
- An image pasted into chat without a file path can't be attached to an email. Ask them to save
  it into the inbox folder (or give a path) and use it from there.

## 2. Inspect every photo
Call `inspect_photo` for each photo. From the image and metadata work out:
- **License plate.** Read it character by character. If any character is unclear, blurry or
  hidden, **ask the user**. Never guess. A wrong plate accuses an uninvolved person.
- **Vehicle type, make, color.** For e-scooters/bikes: rental (logo: Tier, Dott, Lime, Bolt, Voi)
  or private.
- **Violation**: match the user's description and what the photo shows to a key from
  `list_violation_types`. If the photo doesn't support the user's claim (e.g. "bike lane" but no
  lane marking visible), say so.
- **Time and place** come from EXIF/GPS. If they're missing (common for photos forwarded through
  messengers), ask. Prefer the reverse-geocoded address; if the user named a better spot
  (an intersection), use theirs. If `in_berlin` is false, stop: this only covers Berlin.
- With 2+ photos of the same vehicle minutes apart, use the earliest as `time_start` and the
  latest as `time_end`.

## 3. Draft
Call `draft_report`. Write `details` and `obstruction` in plain, factual **German**. Only
include what was observed, no opinions, e.g. `"Fußgänger mit Kinderwagen mussten auf die
Fahrbahn ausweichen"`. Leave `obstruction` empty if nobody was actually obstructed.

## 4. Show the draft and confirm
Show the user, briefly:
- where it goes (authority + email, or "web form, you submit")
- plate, vehicle, violation, time, place, number of photos
- every item in `warnings`
Then ask: "Submit?" Don't show the full German letter unless they ask for it or it's their first
report.

## 5. Submit
Only after an explicit yes, call `submit_report(draft_id, user_confirmed=true)`.
- `sent`: confirm; they got a CC copy.
- `dry_run`: tell them it was saved to the outbox, not sent, and how to switch it on
  (`DRY_RUN=0`).
- `form_pending` (moving violations → Polizei Internetwache; rental scooters → operator form):
  submit the web form yourself, see below.

## 6. Web forms (`form_pending`)
Use the `playwright` MCP browser tools. The browser window is visible on the user's screen.
1. `browser_navigate` to `start_url`, then `browser_snapshot` to read the page. Follow
   `form_hints` but trust what the page actually says; labels change.
2. Fill each field from the payload (`reporter`, `incident`, `vehicle`). Put `description_de`
   in the free-text field (Sachverhalt/Beschreibung/Kommentar). To upload photos, first
   `browser_click` the upload button/field (this opens a file chooser), then call
   `browser_file_upload` with `upload_files`. Split or reformat values as the field requires (e.g. date formats).
3. Choose options that match the facts. The user is a **witness**, not a victim. Tick
   declarations that the information is truthful or that they are willing to testify; the
   report already says both. Decline newsletters and optional marketing.
4. **Stop and ask the user** if:
   - the form requires something not in the payload (e.g. birth date). Suggest they store it
     with `berlin-reporter-secrets set REPORTER_BIRTHDATE`;
   - a choice doesn't clearly fit the facts, or a declaration goes beyond "truthful / willing to
     testify";
   - there is a **CAPTCHA**. Ask them to solve it in the browser window, then continue. Never
     try to solve or bypass it.
5. On the final review page, `browser_snapshot` and check plate, date, time and place against
   the draft. If everything matches what the user already approved, click Absenden/Senden. If
   anything differs, fix it or ask.
6. On the confirmation page, read any Vorgangsnummer/reference and call
   `mark_web_submitted(draft_id, reference)`. Tell the user it went through, with the reference.
   If submission failed, say so plainly and don't call `mark_web_submitted`.

## Rules
- Reports go out under the user's real name and they may be called as a witness. False
  accusations are a criminal offence (§ 164 StGB). When unsure, ask rather than submit.
- Acute danger, an accident or an emergency: tell them to call 110, not to file a report.
- If `setup_status` shows missing reporter or SMTP fields, walk them through `.env` first.
- Several vehicles in one photo means one report per vehicle.
