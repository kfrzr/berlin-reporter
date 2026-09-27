# berlin-reporter

Report illegally parked or driven cars, motorcycles, mopeds and e-scooters in Berlin from a
photo. Send Claude a photo and a sentence ("blocking the bike lane on Oranienstraße"). Claude
reads the plate, the time and the GPS position, writes the report in German, picks the right
authority, and submits it once you say yes.

It consists of:

- an **MCP server** (`src/berlin_reporter`) that reads photo metadata, drafts the report, and
  emails it with the photos attached;
- a **skill** (`.claude/skills/report-violation`) that tells Claude the workflow and the rules
  (never guess a plate, always confirm before sending).

## Where reports go

| What | Who handles it | How |
|---|---|---|
| Stopping/parking violations by cars, vans, trucks, motorcycles, mopeds, private e-scooters | Polizei Berlin, Zentrale Bußgeldstelle | Email to `anzeige@bowi.berlin.de`, sent automatically with photos, you in CC |
| Moving violations (red light, phone at the wheel, driving on the sidewalk or bike lane, close passes, …) | Polizei Berlin, [Internetwache](https://www.internetwache-polizei-berlin.de/) | Web form: Claude prepares the text, you paste it and upload the photos |
| Misparked rental e-scooters/bikes | The operator, via the [Jelbi form](https://www.jelbi.de/en/parking-violations-of-two-wheelers/) or [scooter-melder.de](https://www.scooter-melder.de/) | Web form, same as above |
| Accidents, injuries, acute danger | Police | Call **110** |

The Bußgeldstelle requires your name and postal address. Anonymous reports are not processed.
You get no feedback on the outcome, and you may be called as a witness. See
[berlin.de: Anzeige erstatten](https://www.berlin.de/polizei/aufgaben/bussgeldstelle/anzeigenerstattung/).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/kfrzr/berlin-reporter && cd berlin-reporter
cp .env.example .env     # fill in your name, address, email and SMTP login
uv sync
```

For Gmail, use an [app password](https://myaccount.google.com/apppasswords) as `SMTP_PASSWORD`
(host `smtp.gmail.com`, port 587). Other providers work the same way.

Nothing is sent while `DRY_RUN=1` (the default). Reports are written as `.eml` files to
`~/berlin-reports/outbox/`, so you can open them in a mail client and check them. When they look
right, set `DRY_RUN=0`.

### Claude Code (in this folder)

Run `claude` inside the repo. `.mcp.json` registers the server and the skill loads automatically.
Approve the `berlin-reporter` server the first time.

### Claude Code (anywhere)

```sh
claude mcp add --scope user berlin-reporter -- uv run --directory "$PWD" berlin-reporter
mkdir -p ~/.claude/skills && cp -r .claude/skills/report-violation ~/.claude/skills/
```

The server also reads `~/.config/berlin-reporter/.env`, so you can keep your settings there.

### Claude Desktop

Add to `claude_desktop_config.json` (use the absolute path to this folder):

```json
{
  "mcpServers": {
    "berlin-reporter": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/berlin-reporter", "berlin-reporter"]
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
| `submit_report` | Sends the email (or dry run). For web-form routes, returns the text and link |
| `report_history` | Lists past reports (`~/berlin-reports/history.jsonl`) |

## Development

```sh
uv run --group dev pytest
```

## Responsibility

Reports go out under your name. Only report what you actually saw. A knowingly false report is
a criminal offence (§ 164 StGB). The skill makes Claude ask when a plate is unclear, and it never
submits without your explicit confirmation.
