# TickTick <-> Google Calendar Sync (`ticktick-gcal-sync`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)](https://python.org)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-orange.svg)]()
[![Systemd: Ready](https://img.shields.io/badge/Systemd-User%20Timer-informational.svg)]()

A lightweight, automated synchronization daemon and CLI tool that seamlessly bridges your **TickTick** tasks with **Google Calendar** on Linux.

---

## 🌟 Highlights & Features

- **🔄 Automatic Background Sync:** Runs silently via a systemd user timer (default: every 10 minutes and on boot). Uses **0 MB RAM** when idle!
- **⚡ Smart Change Detection:** Postponed or rescheduled a task in TickTick on your phone? The corresponding event and popup reminders in Google Calendar are automatically updated.
- **⏰ Full Reminder Support:** Tasks with due dates get converted to Google Calendar events with customizable popup notifications.
- **✅ Completion Tracking:** Tasks marked as completed in TickTick are gracefully flagged in Google Calendar (`[انجام شد]`).
- **🐧 Multi-Format Linux Support:** Automatically detects TickTick configuration across **Flatpak**, **Snap**, and native installations.
- **🛡️ Proxy & SOCKS5 Aware:** Native fallback and support for SOCKS5 proxies (`socks5://127.0.0.1:2080`), ensuring reliable sync even in restricted networks.
- **💻 Powerful CLI (`sync-task`):** Create, list, sync, and inspect tasks and calendar events directly from your terminal.

---

## 📋 Prerequisites

1. **Linux** with systemd (Arch, Ubuntu, Fedora, Debian, etc.).
2. **TickTick Desktop** installed and logged in (Flatpak, Snap, or Native).
3. **Google Cloud OAuth 2.0 Credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/).
   - Enable **Google Calendar API**.
   - Under **OAuth consent screen**, set user type to **External** and add your Gmail address as a **Test User**.
   - Under **Credentials**, create an **OAuth Client ID** with type **Desktop app**.
   - Download the JSON file and save it as `credentials.json`.

---

## 🚀 Quick Installation

Clone this repository and run the automated installer:

```bash
git clone git@github.com:abbasi0abolfazl/ticktick-gcal-sync.git
cd ticktick-gcal-sync
chmod +x install.sh
./install.sh
```

The script will:
1. Create a Python virtual environment and install dependencies.
2. Install the `sync-task` CLI command into `~/.local/bin/sync-task`.
3. Install and activate the `ticktick-gcal-sync.timer` systemd user service.

---

## 🔑 Authentication

Place your downloaded Google OAuth `credentials.json` into:

```bash
cp /path/to/downloaded/credentials.json ~/.config/ticktick-gcal-sync/credentials.json
```

Then trigger the one-time authentication flow:

```bash
sync-task auth-google
```

A browser window will open. Sign in with your Google account and approve the Calendar access. The resulting token will be saved securely at `~/.config/ticktick-gcal-sync/token.json`.

---

## 🛠️ CLI Usage Reference

The `sync-task` command is available system-wide:

### 1. Manual Sync
```bash
sync-task sync
```

### 2. Add a Task (TickTick + Google Calendar Sync)
```bash
sync-task add-task \
  --title "Client Meeting" \
  --notes "Discuss Q4 Roadmap" \
  --list "Contract" \
  --date "2026-09-24" \
  --time "14:30" \
  --reminder 15 \
  --sync-gcal
```

### 3. List Active Tasks
```bash
sync-task list-tasks --limit 10
```

### 4. List Upcoming Google Calendar Events
```bash
sync-task list-gcal
```

### 5. List TickTick Projects / Lists
```bash
sync-task list-projects
```

---

## ⏱️ Managing the Background Daemon

Since the sync runs via systemd user timers, you can check its status and logs anytime:

```bash
# Check timer status & next scheduled run
systemctl --user status ticktick-gcal-sync.timer

# View sync execution logs
journalctl --user -u ticktick-gcal-sync.service -n 20 --no-pager

# Run an immediate manual sync via systemd
systemctl --user start ticktick-gcal-sync.service
```

---

## 📂 Project Structure

```text
ticktick-gcal-sync/
├── sync_manager.py     # Core sync engine, TickTick & GCal API clients, CLI
├── install.sh          # One-step automated installer
├── requirements.txt    # Python dependencies
├── pyproject.toml      # Project metadata
├── systemd/
│   ├── ticktick-gcal-sync.service
│   └── ticktick-gcal-sync.timer
├── LICENSE             # MIT License
└── README.md           # Documentation
```

---

## 🔒 Security & Privacy

Your credentials and tokens are stored exclusively on your local machine:
- `credentials.json` & `token.json` are kept in `~/.config/ticktick-gcal-sync/` and are strictly excluded via `.gitignore`.
- No sensitive data is ever uploaded or transmitted to third-party servers.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Created with ❤️ by [Abolfazl Abbasi](https://github.com/abbasi0abolfazl).
