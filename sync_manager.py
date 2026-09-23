#!/usr/bin/env python3
"""
TickTick <-> Google Calendar Sync Tool
Synchronizes TickTick tasks to Google Calendar with reminders and periodic background sync.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# SOCKS proxy fallback if run under systemd without shell env
if "https_proxy" not in os.environ and "HTTPS_PROXY" not in os.environ:
    if os.path.exists("/proc/net/tcp"):
        # Check if local proxy on 2080 or standard ports exist, or set gracefully
        os.environ["https_proxy"] = "socks5://127.0.0.1:2080"
        os.environ["http_proxy"] = "socks5://127.0.0.1:2080"
        os.environ["all_proxy"] = "socks5://127.0.0.1:2080"

HOME_DIR = str(Path.home())
CONFIG_DIR = os.environ.get(
    "TICKTICK_GCAL_CONFIG_DIR",
    os.path.join(HOME_DIR, ".config", "ticktick-gcal-sync")
)
os.makedirs(CONFIG_DIR, exist_ok=True)

CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CONFIG_DIR, "token.json")
SYNC_STATE_FILE = os.path.join(CONFIG_DIR, "sync_state.json")
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def find_ticktick_config():
    """Locate TickTick config.json across common Linux installation types."""
    possible_paths = [
        # Flatpak
        os.path.join(HOME_DIR, ".var/app/com.ticktick.TickTick/config/ticktick/config.json"),
        # Native / Arch / AUR
        os.path.join(HOME_DIR, ".config/ticktick/config.json"),
        os.path.join(HOME_DIR, ".config/TickTick/config.json"),
        # Snap
        os.path.join(HOME_DIR, "snap/ticktick/current/.config/ticktick/config.json"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return None


# --- TickTick Client ---
class TickTickClient:
    def __init__(self, config_path=None):
        self.config_path = config_path or find_ticktick_config()
        if not self.config_path or not os.path.exists(self.config_path):
            raise RuntimeError(
                f"TickTick config file not found.\n"
                f"Please ensure TickTick is installed and logged in."
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.token = data.get("token")
        self.device_id = data.get("deviceId")
        self.inbox_id = data.get("globalUser", {}).get("inboxId")
        self.user_id = data.get("globalUser", {}).get("userId")

        self.headers = {
            "Cookie": f"t={self.token}",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "x-device": json.dumps({
                "platform": "web",
                "os": "Linux",
                "device": "Chrome",
                "name": "ticktick-agent",
                "version": 5000,
                "id": self.device_id,
                "channel": "website",
                "campaign": "",
                "websocket": ""
            }),
            "Content-Type": "application/json"
        }

    def get_projects(self):
        url = "https://api.ticktick.com/api/v2/projects"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def get_tasks(self):
        url = "https://api.ticktick.com/api/v2/batch/check/0"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("syncTaskBean", {}).get("update", [])

    def create_task(self, title, content="", project_id=None, due_datetime=None, is_all_day=False, reminder_minutes=None, time_zone="Asia/Tehran"):
        if not project_id:
            project_id = self.inbox_id

        task = {
            "title": title,
            "content": content,
            "projectId": project_id,
            "timeZone": time_zone
        }

        if due_datetime:
            tz = pytz.timezone(time_zone)
            if due_datetime.tzinfo is None:
                local_dt = tz.localize(due_datetime)
            else:
                local_dt = due_datetime.astimezone(tz)

            utc_dt = local_dt.astimezone(pytz.utc)
            task["dueDate"] = utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
            task["isAllDay"] = is_all_day

            if reminder_minutes is not None:
                trigger = "TRIGGER:PT0S" if reminder_minutes == 0 else f"TRIGGER:-PT{reminder_minutes}M"
                task["reminders"] = [{"id": "r1", "trigger": trigger}]

        url = "https://api.ticktick.com/api/v2/task"
        payload = json.dumps(task).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=self.headers)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def complete_task(self, task_id, project_id):
        url = "https://api.ticktick.com/api/v2/batch/task"
        payload = json.dumps({
            "update": [{
                "id": task_id,
                "projectId": project_id,
                "status": 2
            }]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=self.headers)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def delete_task(self, task_id, project_id):
        url = "https://api.ticktick.com/api/v2/batch/task"
        payload = json.dumps({
            "delete": [{
                "taskId": task_id,
                "projectId": project_id
            }]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=self.headers)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())


# --- Google Calendar Client ---
class GoogleCalendarClient:
    def __init__(self):
        self.service = None

    def is_configured(self):
        return os.path.exists(TOKEN_FILE) or os.path.exists(CREDENTIALS_FILE)

    def has_token(self):
        return os.path.exists(TOKEN_FILE)

    def authenticate(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    raise FileNotFoundError(
                        f"credentials.json not found in {CONFIG_DIR}.\n"
                        f"Please place your Google OAuth credentials JSON file at:\n"
                        f"'{CREDENTIALS_FILE}'"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                print("\nOpening browser for Google authorization...")
                print("If the browser does not open automatically, visit the URL provided below:")
                sys.stdout.flush()
                creds = flow.run_local_server(host='localhost', port=0, prompt="consent")

            with open(TOKEN_FILE, "w", encoding="utf-8") as token:
                token.write(creds.to_json())

        from googleapiclient.discovery import build
        self.service = build("calendar", "v3", credentials=creds)
        return self.service

    def get_service(self):
        if not self.service:
            self.authenticate()
        return self.service

    def create_event(self, summary, description="", start_datetime=None, end_datetime=None, reminder_minutes=15, time_zone="Asia/Tehran"):
        service = self.get_service()
        tz = pytz.timezone(time_zone)

        if start_datetime is None:
            start_datetime = datetime.now() + timedelta(hours=1)
        if end_datetime is None:
            end_datetime = start_datetime + timedelta(minutes=30)

        if start_datetime.tzinfo is None:
            start_datetime = tz.localize(start_datetime)
        if end_datetime.tzinfo is None:
            end_datetime = tz.localize(end_datetime)

        event = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": time_zone,
            },
            "end": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": time_zone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": reminder_minutes},
                ],
            },
        }

        created_event = service.events().insert(calendarId="primary", body=event).execute()
        return created_event

    def list_upcoming_events(self, max_results=10, time_zone="Asia/Tehran"):
        service = self.get_service()
        now = datetime.now(pytz.timezone(time_zone)).isoformat()
        events_result = service.events().list(
            calendarId="primary", timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy="startTime"
        ).execute()
        return events_result.get("items", [])


# --- Periodic Sync Logic ---
def sync_tasks_to_gcal(time_zone="Asia/Tehran"):
    state = {}
    if os.path.exists(SYNC_STATE_FILE):
        try:
            with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}

    tt = TickTickClient()
    gcal = GoogleCalendarClient()
    if not gcal.has_token():
        print("Google Calendar token missing. Please run 'sync-task auth-google'.")
        return

    service = gcal.get_service()
    tasks = tt.get_tasks()
    tz = pytz.timezone(time_zone)

    synced_count = 0
    updated_count = 0

    for t in tasks:
        task_id = t.get("id")
        title = t.get("title", "").strip()
        due_str = t.get("dueDate")
        status = t.get("status", 0)

        if not title:
            continue

        if due_str and status == 0:
            try:
                clean_due = due_str.split(".")[0].replace("Z", "")
                due_utc = datetime.strptime(clean_due, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
                local_dt = due_utc.astimezone(tz)
                end_dt = local_dt + timedelta(minutes=30)
            except Exception as e:
                print(f"Error parsing date {due_str} for '{title}': {e}")
                continue

            if task_id in state:
                prev_due = state[task_id].get("dueDate")
                prev_title = state[task_id].get("title")
                gcal_id = state[task_id].get("gcal_id")

                if prev_due != due_str or prev_title != title:
                    print(f"Detected change in '{title}': updating Google Calendar event {gcal_id}...")
                    try:
                        ev = service.events().get(calendarId="primary", eventId=gcal_id).execute()
                        ev["summary"] = title
                        ev["start"] = {"dateTime": local_dt.isoformat(), "timeZone": time_zone}
                        ev["end"] = {"dateTime": end_dt.isoformat(), "timeZone": time_zone}
                        service.events().update(calendarId="primary", eventId=gcal_id, body=ev).execute()
                        state[task_id]["dueDate"] = due_str
                        state[task_id]["title"] = title
                        state[task_id]["status"] = 0
                        updated_count += 1
                        print(f"✓ Updated '{title}' to {local_dt.strftime('%Y-%m-%d %H:%M')}")
                    except Exception as e:
                        print(f"Error updating event {gcal_id}: {e}")
            else:
                existing_events = service.events().list(
                    calendarId="primary",
                    q=title,
                    timeMin=(local_dt - timedelta(days=2)).isoformat(),
                    timeMax=(local_dt + timedelta(days=2)).isoformat(),
                    singleEvents=True
                ).execute().get("items", [])

                gcal_id = None
                for ev in existing_events:
                    if ev.get("summary") == title:
                        gcal_id = ev.get("id")
                        break

                if gcal_id:
                    print(f"Linked existing Google Calendar event for '{title}' (ID: {gcal_id})")
                    state[task_id] = {
                        "gcal_id": gcal_id,
                        "title": title,
                        "dueDate": due_str,
                        "status": 0
                    }
                    updated_count += 1
                else:
                    print(f"Adding new task with due date to Google Calendar: '{title}'...")
                    try:
                        ev = gcal.create_event(
                            summary=title,
                            description=t.get("content", "") or "",
                            start_datetime=local_dt,
                            end_datetime=end_dt,
                            reminder_minutes=15,
                            time_zone=time_zone
                        )
                        state[task_id] = {
                            "gcal_id": ev.get("id"),
                            "title": title,
                            "dueDate": due_str,
                            "status": 0
                        }
                        synced_count += 1
                        print(f"✓ Created '{title}' in Google Calendar")
                    except Exception as e:
                        print(f"Error creating event for '{title}': {e}")

        elif status == 2 and task_id in state and state[task_id].get("status") != 2:
            gcal_id = state[task_id].get("gcal_id")
            try:
                ev = service.events().get(calendarId="primary", eventId=gcal_id).execute()
                if not ev.get("summary", "").startswith("[انجام شد]"):
                    ev["summary"] = f"[انجام شد] {ev.get('summary')}"
                    service.events().update(calendarId="primary", eventId=gcal_id, body=ev).execute()
                state[task_id]["status"] = 2
                updated_count += 1
                print(f"✓ Marked '{title}' as completed in Google Calendar")
            except Exception as e:
                print(f"Notice: Could not mark completed for {task_id}: {e}")

    with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"Sync complete. New events: {synced_count}, Updated events: {updated_count}")


def main():
    parser = argparse.ArgumentParser(description="TickTick and Google Calendar Sync CLI")
    subparsers = parser.add_subparsers(dest="command")

    # auth command
    subparsers.add_parser("auth-google", help="Authenticate with Google Calendar")

    # sync command
    subparsers.add_parser("sync", help="Synchronize all TickTick tasks with Google Calendar")

    # list-projects
    subparsers.add_parser("list-projects", help="List TickTick projects/lists")

    # list-tasks
    list_tasks_parser = subparsers.add_parser("list-tasks", help="List active tasks from TickTick")
    list_tasks_parser.add_argument("--limit", type=int, default=15, help="Number of tasks to show")

    # list-gcal
    subparsers.add_parser("list-gcal", help="List upcoming events from Google Calendar")

    # add-task
    add_parser = subparsers.add_parser("add-task", help="Add a task to TickTick and optionally Google Calendar")
    add_parser.add_argument("--title", required=True, help="Task title")
    add_parser.add_argument("--notes", default="", help="Task notes or description")
    add_parser.add_argument("--list", default=None, help="TickTick list name (e.g., 'Inbox', 'Personal')")
    add_parser.add_argument("--date", default=None, help="Due date (YYYY-MM-DD)")
    add_parser.add_argument("--time", default=None, help="Due time (HH:MM) in 24h format")
    add_parser.add_argument("--duration", type=int, default=30, help="Duration in minutes for Google Calendar event")
    add_parser.add_argument("--reminder", type=int, default=15, help="Reminder minutes before due time (default: 15)")
    add_parser.add_argument("--sync-gcal", action="store_true", help="Also add to Google Calendar")
    add_parser.add_argument("--timezone", default="Asia/Tehran", help="Timezone (default: Asia/Tehran)")

    args = parser.parse_args()

    if args.command == "auth-google":
        gcal = GoogleCalendarClient()
        print("Starting Google Calendar authentication...")
        gcal.authenticate()
        print("Successfully authenticated and token saved!")

    elif args.command == "sync":
        sync_tasks_to_gcal()

    elif args.command == "list-projects":
        tt = TickTickClient()
        projects = tt.get_projects()
        print(f"Total projects: {len(projects)}")
        for p in projects:
            print(f"- [{p.get('id')}] {p.get('name')}")

    elif args.command == "list-tasks":
        tt = TickTickClient()
        tasks = tt.get_tasks()
        active = [t for t in tasks if t.get("status") == 0 and t.get("title")]
        print(f"Active Tasks ({len(active)}):")
        for t in active[:args.limit]:
            due = t.get("dueDate", "No due date")
            print(f"- {t.get('title')} (Due: {due})")

    elif args.command == "list-gcal":
        gcal = GoogleCalendarClient()
        events = gcal.list_upcoming_events()
        print(f"Upcoming events ({len(events)}):")
        for ev in events:
            start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date"))
            print(f"- {ev.get('summary')} at {start} (ID: {ev.get('id')})")

    elif args.command == "add-task":
        tt = TickTickClient()
        project_id = None
        if args.list:
            projects = tt.get_projects()
            for p in projects:
                if p.get("name", "").lower() == args.list.lower():
                    project_id = p.get("id")
                    break
            if not project_id:
                print(f"Warning: List '{args.list}' not found. Falling back to Inbox.")

        due_dt = None
        is_all_day = False
        if args.date:
            if args.time:
                due_dt = datetime.strptime(f"{args.date} {args.time}", "%Y-%m-%d %H:%M")
                is_all_day = False
            else:
                due_dt = datetime.strptime(args.date, "%Y-%m-%d")
                is_all_day = True

        print(f"Creating TickTick task: '{args.title}'...")
        tt_res = tt.create_task(
            title=args.title,
            content=args.notes,
            project_id=project_id,
            due_datetime=due_dt,
            is_all_day=is_all_day,
            reminder_minutes=args.reminder if due_dt and not is_all_day else None,
            time_zone=args.timezone
        )
        task_id = tt_res.get("id")
        print(f"✓ Created in TickTick! Task ID: {task_id}")

        if args.sync_gcal:
            gcal = GoogleCalendarClient()
            if not gcal.is_configured():
                print("Notice: Google Calendar is not configured yet. Run 'auth-google' first.")
            else:
                start_dt = due_dt if due_dt and not is_all_day else datetime.now()
                end_dt = start_dt + timedelta(minutes=args.duration)
                print(f"Creating Google Calendar event: '{args.title}'...")
                gcal_res = gcal.create_event(
                    summary=args.title,
                    description=args.notes,
                    start_datetime=start_dt,
                    end_datetime=end_dt,
                    reminder_minutes=args.reminder,
                    time_zone=args.timezone
                )
                gcal_id = gcal_res.get("id")
                print(f"✓ Created in Google Calendar! Event link: {gcal_res.get('htmlLink')}")

                state = {}
                if os.path.exists(SYNC_STATE_FILE):
                    try:
                        with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
                            state = json.load(f)
                    except Exception:
                        pass
                state[task_id] = {
                    "gcal_id": gcal_id,
                    "title": args.title,
                    "dueDate": tt_res.get("dueDate"),
                    "status": 0
                }
                with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
