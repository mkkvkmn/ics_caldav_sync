# ICS to CalDAV synchronisation
Downloads a calendar in ICS format and uploads it to a CalDAV server, regularly.
Your employee, school, or whoever shares a calendar as a link to an ICS file
and you'd like to have it on another CalDAV server?
Look no further.

## Standalone usage
Install requirements from `requirements.txt` and run `sync.py` file
using Python 3.8 or higher.

Set the settings as environment variables:
* REMOTE_URL (str): ICS file URL.
* LOCAL_URL (str): CalDAV URL.
* LOCAL_CALENDAR_NAME (str): The name of your CalDAV calendar.
* LOCAL_USERNAME (str): CalDAV username.
* LOCAL_PASSWORD (str): CalDAV password.
* REMOTE_USERNAME (str, optional): ICS host username.
* REMOTE_PASSWORD (str, optional): ICS host password.
* SYNC_EVERY (str): How often should the synchronisation occur? For example: 2 minutes, 1 hour. Synchronise once if empty.

## Rationale
Couldn't think of a better way to sync multiple o365 calendars with my caldav server.
