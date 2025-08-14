## Dark Galaxy Command Box

Run `ticket_gui.py` to launch the Dark Galaxy Command Box, a small Windows-friendly GUI for ticket submission and server management. The window sports a dark background with neon green text for a hacker vibe and a stats panel in the top-right showing how many main and alt IDs have been stored.

1. Enter a main ID in the text box.
2. Click **Send** or press **Enter**.
3. A prompt will ask if you want to add any alt IDs.
4. If yes, enter alt IDs separated by commas and submit.

Each ID must be unique. Mains are stored with a `USER` rank and alts with an `ALT` rank. If a main or alt ID already exists, a message will inform you and the entry will be rejected.

To view existing IDs, type either a main or alt ID and click **Load Alts**. The window will display the main ID and all associated alt IDs if the ID has been previously stored.

Use the **Commands** dropdown to choose an action and press **Build**. Hovering over the dropdown shows a short description of the selected command.

Available commands:

- **Set User Ranks** – writes `set_user_ranks.bat`, updating the `userRank` field in the `game_account` collection for each stored ID.
- **Add 100/200/500/1000/2500/5000/10000 Champion Points** – each option generates a batch file that adds the specified amount of `championPoints` to every user in `game_users` via `game_resources.championPoints`.

All IDs are saved to `ids.json` in the working directory and reloaded on subsequent launches so you can build on previous submissions.

This script uses Python's built-in `tkinter` library.

### Backup and Restore

Run `sync_server.py` on the machine that will store backups. Launching the script opens a small status window (300×120) that shows the listening port, server uptime, and a colored dot indicating sync health—green when client hashes match, yellow for minor timestamp drift, and red if the hash is invalid or the server stops. It listens on port `1981` using HTTPS and keeps the newest version of each file based on its timestamp. A self-signed certificate (`server.crt` and `server.key`) is provided for local testing; generate your own pair for production use.

In the GUI, use the **Backup** button to upload all local files (excluding Git metadata) to the server. The **Load Backup** button downloads any newer files from the server and replaces outdated copies locally. After each download the client computes a SHA-256 hash of the archive and posts it back to the server for verification. The server compares the hash with its own copy and replies with one of three statuses:

- **green** – hashes match; normal operation and backups are allowed
- **yellow** – hashes differ but the backup is less than a day old; the client remains usable but skips automatic backups
- **red** – hashes differ and the backup is stale; the GUI disables all functions

The client verifies the server certificate, and you can override the default server URL by setting the `SYNC_SERVER` environment variable. When the GUI launches it pulls the latest files, verifies them, and only uploads a backup on exit if the server reports a green status.

### Installation

For convenience, setup scripts are provided:

- `install_client.sh` creates a virtual environment and installs the client dependencies.
- `install_server.sh` prepares a virtual environment with Flask for the backup server.

Run the appropriate script and then launch `ticket_gui.py` or `sync_server.py` from the created `venv`.
