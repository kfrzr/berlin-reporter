# berlin-reporter

Report illegally parked or driven cars, motorcycles, mopeds and e-scooters in Berlin from a
photo. Send Claude a photo and a sentence ("blocking the bike lane on Oranienstraße"). Claude
reads the plate, the time and the GPS position, writes the report in German, picks the right
authority, and submits it once you say yes.

It consists of:

- an **MCP server** (`src/berlin_reporter`) that reads photo metadata, drafts the report,
  emails it with the photos attached, and prepares the data for web forms;
- the **[Playwright MCP](https://github.com/microsoft/playwright-mcp)** browser, which Claude
  uses to fill in and submit the web forms (police online station, scooter operators);
- a **skill** (`.claude/skills/report-violation`) that tells Claude the workflow and the rules
  (never guess a plate, always confirm before sending).

## Where reports go

| What | Who handles it | How |
|---|---|---|
| Stopping/parking violations by cars, vans, trucks, motorcycles, mopeds, private e-scooters | Polizei Berlin, Zentrale Bußgeldstelle | Email to `anzeige@bowi.berlin.de`, sent automatically with photos, you in CC |
| Moving violations (red light, phone at the wheel, driving on the sidewalk or bike lane, close passes, …) | Polizei Berlin, [Internetwache](https://www.internetwache-polizei-berlin.de/) | Web form, filled in and submitted by Claude in a browser window on your screen |
| Misparked rental e-scooters/bikes | The operator, via the [Jelbi form](https://www.jelbi.de/en/parking-violations-of-two-wheelers/) or [scooter-melder.de](https://www.scooter-melder.de/) | Web form, same as above |
| Accidents, injuries, acute danger | Police | Call **110** |

The Bußgeldstelle requires your name and postal address. Anonymous reports are not processed.
You get no feedback on the outcome, and you may be called as a witness. See
[berlin.de: Anzeige erstatten](https://www.berlin.de/polizei/aufgaben/bussgeldstelle/anzeigenerstattung/).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and, for web forms, [Node.js](https://nodejs.org/) 18+
(for `npx`).

```sh
git clone https://github.com/kfrzr/berlin-reporter && cd berlin-reporter
uv sync
uv run berlin-reporter-secrets set   # name, address, email, SMTP login → OS keychain
cp .env.example .env                 # non-secret settings (SMTP host, DRY_RUN, ...)
```

### Where your personal data lives

This repository is public, so your name, address and passwords must never be committed. They
live only on your computer:

- **OS keychain (recommended).** `berlin-reporter-secrets set` stores them in the macOS
  Keychain, Windows Credential Manager, or the Linux Secret Service. Use
  `berlin-reporter-secrets show` to check what's stored and `delete KEY` to remove an entry.
- **`.env` file.** It is in `.gitignore`, so git never picks it up. Anything set here or as a
  real environment variable overrides the keychain.

GitHub repository secrets would not help here: only GitHub Actions and Codespaces can read
them, not a server running on your computer. For Claude Code on the web (cloud sessions), set
them as environment variables in the cloud environment's settings instead. They are stored with
your account, not in the repo. The web-form flow still needs a local browser, though.

For Gmail, use an [app password](https://myaccount.google.com/apppasswords) as `SMTP_PASSWORD`
(host `smtp.gmail.com`, port 587). Other providers work the same way.

Nothing is sent while `DRY_RUN=1` (the default). Reports are written as `.eml` files to
`~/berlin-reports/outbox/`, so you can open them in a mail client and check them. When they look
right, set `DRY_RUN=0`.

### Claude Code (in this folder)

Run `claude` inside the repo. `.mcp.json` registers the server and the skill loads automatically.
Approve the `berlin-reporter` and `playwright` servers the first time.

### Claude Code (anywhere)

```sh
claude mcp add --scope user berlin-reporter -- uv run --directory "$PWD" berlin-reporter
claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --allow-unrestricted-file-access
mkdir -p ~/.claude/skills && cp -r .claude/skills/report-violation ~/.claude/skills/
```

By default the Playwright browser may only upload files from the folder Claude was started in.
Photos are staged in this repo's `.uploads/`, so outside this folder it needs
`--allow-unrestricted-file-access`. The alternative is to set `UPLOAD_DIR` to a folder inside
your working directory.

The server also reads `~/.config/berlin-reporter/.env`, so you can keep your settings there.

### Claude Desktop

Add to `claude_desktop_config.json` (use the absolute path to this folder):

```json
{
  "mcpServers": {
    "berlin-reporter": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/berlin-reporter", "berlin-reporter"]
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--allow-unrestricted-file-access"]
    }
  }
}
```

To use the skill there too, zip `.claude/skills/report-violation` and upload it under
Settings → Capabilities → Skills.

## Getting photos from your phone

The server has to read the actual photo file, because an image pasted into a chat can't be
attached to an email. The simplest setup is to point `REPORTS_DIR` at a folder your phone syncs
to (iCloud Drive, Dropbox, Syncthing, …) and drop photos into its `inbox/` subfolder. Then just
say:

> report the latest photo — SUV on the bike lane, cyclists had to swerve into traffic

Keep the original photo when you share it. Messengers such as WhatsApp strip the time and GPS
data, and Claude will then have to ask you for them.

Tips for photos that hold up:

- Make the plate readable in at least one photo, and make the violation visible in context
  (lane marking, sign, curb).
- For parking, take a second photo a few minutes later. It shows the vehicle was parked, not
  just stopping briefly.

## Tools

| Tool | Does |
|---|---|
| `setup_status` | Shows which settings are missing |
| `list_inbox_photos` | Lists the newest photos in the inbox |
| `inspect_photo` | Returns the image plus capture time, GPS, address and Bezirk (via OpenStreetMap) |
| `list_violation_types` | Lists violation keys, vehicle types and routing |
| `draft_report` | Validates the input, picks the authority, writes the German report, and warns about duplicates, odd plates or a missing second observation |
| `submit_report` | Sends the email (or dry run). For web-form routes, returns the form payload (split name and address fields, German description, photos staged as JPEG) for Claude to fill in with the browser |
| `mark_web_submitted` | Records a web-form submission with its reference number and deletes the staged photos |
| `report_history` | Lists past reports (`~/berlin-reports/history.jsonl`) |

## Development

```sh
uv run --group dev pytest
```

## Responsibility

Reports go out under your name. Only report what you actually saw. A knowingly false report is
a criminal offence (§ 164 StGB). The skill makes Claude ask when a plate is unclear, and it never
submits without your explicit confirmation.

## How web-form submission works

1. You confirm the draft. `submit_report` returns the form data and stages the photos.
2. Claude opens the form in a visible browser window, fills it in step by step, and uploads the
   photos.
3. If there's a CAPTCHA, Claude asks you to solve it in that window. It never tries to solve or
   bypass one. It also stops and asks if the form wants something it doesn't have (some police
   forms ask for your birth date: `berlin-reporter-secrets set REPORTER_BIRTHDATE`), or if an
   option doesn't clearly fit.
4. Claude checks the review page against the draft you approved, submits, and records the
   reference number (`mark_web_submitted`).

Claude reads each form as it loads rather than using hard-coded field names, so small layout
changes on the sites don't break it.
