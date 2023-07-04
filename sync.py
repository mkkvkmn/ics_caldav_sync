import os
import sys
import time
import re
from typing import Set

import arrow
import caldav
import ics
import requests
from ics.icalendar import Event
from dateutil.rrule import rrulestr
from dateutil.parser import parse
from dateutil.tz import tzutc



class ICSToCalDAV:
    """
    Downloads a calendar in ICS format and uploads it to a CalDAV server.
    Your employee, school, or whoever shares a calendar as an ICS file
    and you'd like to have it on another CalDAV server?
    Look no further.

    Arguments:
    * remote_urls (list): ICS file URLs.
    * local_url (str): CalDAV URL.
    * local_calendar_name (str): The name of your CalDAV calendar.
    * local_username (str): CalDAV username.
    * local_password (str): CalDAV password.
    * remote_username (str, optional): ICS host username.
    * remote_password (str, optional): ICS host password.
    """

    def __init__(
        self,
        *,
        remote_urls: list,
        local_url: str,
        local_calendar_name: str,
        local_username: str,
        local_password: str,
        remote_username: str = "",
        remote_password: str = "",
    ):
        self.local_client = caldav.DAVClient(
            url=local_url,
            auth=(local_username.encode(), local_password.encode()),
        )

        self.local_calendar = self.local_client.principal().calendar(
            local_calendar_name
        )

        self.remote_calendars = {}
        for url, id in remote_urls:
            self.remote_calendars[url] = {
                "calendar": ics.Calendar(
                    requests.get(
                        url,
                        auth=(remote_username.encode(), remote_password.encode()),
                    ).text
                ),
                "id": id
            }

    def _get_local_events_ids(self) -> Set[int]:
        """
        This piece of crap:
        1) Gets from the local calendar all the events ocurring after now,
        2) Loads them to ics library so their UID can be pulled,
        3) Pulls all of the UIDs and returns them.
        """
        local_events = self.local_calendar.date_search(arrow.utcnow())
        local_events_ids = set(
            next(iter(ics.Calendar(e.data).events)).uid for e in local_events
        )
        return local_events_ids

    @staticmethod
    def _wrap(vevent: str) -> str:
        """
        Since CalDAV expects a VEVENT in a VCALENDAR,
        we need to wrap each event pulled from a single ICS
        into its own calendar. Also added VTIMEZONE.
        """
        vtimezone = """
            BEGIN:VTIMEZONE
            TZID:Europe/Helsinki
            BEGIN:DAYLIGHT
            TZOFFSETFROM:+0200
            RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
            DTSTART:19810329T030000
            TZNAME:EEST
            TZOFFSETTO:+0300
            END:DAYLIGHT
            BEGIN:STANDARD
            TZOFFSETFROM:+0300
            RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
            DTSTART:19811025T040000
            TZNAME:EET
            TZOFFSETTO:+0200
            END:STANDARD
            END:VTIMEZONE
        """
        result = f"""
            BEGIN:VCALENDAR
            VERSION:2.0
            PRODID:-//Chihiro Software Ltd//Calendar sync//EN
            {vtimezone}
            {vevent}
            END:VCALENDAR
        """
        return "\n".join(line.lstrip() for line in result.split("\n"))


    @staticmethod
    def get_event_end(vevent):
        """
        Event end date might be earlier than the until date, 
        the actual end date of recurring event. Find latest.
        """
        rrule_str = None
        until_date = None

        # find RRULE
        event_str = str(vevent)
        for line in event_str.splitlines():
            if line.startswith('RRULE:'):
                rrule_str = line.split("RRULE:")[1]

        # find until date
        if rrule_str:
            rrule = rrulestr(rrule_str, dtstart=vevent.begin.datetime)
            until_date = rrule._until

        # get actual end date
        max_date = vevent.end if until_date is None else max(vevent.end, until_date)
        # print('max_date',max_date)

        return max_date


    def synchronise(self):
        print('.synchronise')
        """
        The main function which:
        1) Pulls all the events from the remote calendar,
        2) Saves them into the local calendar,
        3) Removes local events which are not in the remote any more.
        """
        for url, remote_calendar_info in self.remote_calendars.items():
            remote_calendar = remote_calendar_info["calendar"]
            id = remote_calendar_info["id"]
            for remote_event in remote_calendar.events:

                if remote_event.name != 'Arvova Dailya':
                    
                    max_date = self.get_event_end(remote_event)

                    if arrow.utcnow().to('Europe/Helsinki') <= max_date:

                        try:
                            # prefix name with id
                            remote_event.name = f"{id}:{remote_event.name}"

                            # create unique UID for recurring events
                            new_uid = f"{id}_{remote_event.uid}" + '||' + str(remote_event.begin.timestamp())

                            # force unique UID for recurring events, keep each event and don't replace based on original UID
                            event_str = str(remote_event)
                            event_str = re.sub(r"UID:[^\n]+",f"UID:{new_uid}",event_str) # replace uid, match "UID:" plus any chars but newline
                            event_str = re.sub(r"RECURRENCE-ID.*\n", "", event_str) # replace recurrence line

                            # use my timezone
                            event_str = re.sub(r"DTSTART:[^\n]+", f"DTSTART;TZID=Europe/Helsinki:{remote_event.begin.strftime('%Y%m%dT%H%M%S')}", event_str)
                            event_str = re.sub(r"DTEND:[^\n]+", f"DTEND;TZID=Europe/Helsinki:{remote_event.end.strftime('%Y%m%dT%H%M%S')}", event_str)
                            event_str = re.sub(r"TZID=FLE Standard Time", f"TZID=Europe/Helsinki", event_str)

                            # check the event
                            # print(self._wrap(event_str))

                            self.local_calendar.save_event(self._wrap(event_str))
                            print(f"+{remote_event.name} ({remote_event.begin})\n", end="")
                            sys.stdout.flush()
                                
                        except Exception as e:
                            print(f"Failed to process event {remote_event.uid}: {e}")
                            continue

            remote_events_ids = set(new_uid for e in remote_calendar.events)
            local_events_ids = set(local_event_id.split('||')[0] for local_event_id in self._get_local_events_ids())
            events_to_delete = local_events_ids - remote_events_ids

            for local_event_id in events_to_delete:
                self.local_client.delete(
                    f"{self.local_calendar.url}{local_event_id}.ics"
                )
                # print(f"-{local_event_id}\n", end="")
                print(f"-", end="")
                sys.stdout.flush()
            print()

       
def getenv_or_raise(var):
    if (value := os.getenv(var)) is None:
        raise Exception(f"Environment variable {var} is unset")
    return value


if __name__ == "__main__":
    print('.set up env')
    remote_url_strings = getenv_or_raise("REMOTE_URLS").split()
    remote_urls = [tuple(s.split(",")) for s in remote_url_strings]
    settings = {
        "remote_urls": remote_urls,
        "local_url": getenv_or_raise("LOCAL_URL"),
        "local_calendar_name": getenv_or_raise("LOCAL_CALENDAR_NAME"),
        "local_username": getenv_or_raise("LOCAL_USERNAME"),
        "local_password": getenv_or_raise("LOCAL_PASSWORD"),
        "remote_username": os.getenv("REMOTE_USERNAME", ""),
        "remote_password": os.getenv("REMOTE_PASSWORD", ""),
    }

    sync_every = os.getenv("SYNC_EVERY", None)
    if sync_every is not None:
        sync_every = "in " + sync_every
        print(f'.sync every {sync_every}')
        try:
            arrow.utcnow().dehumanize(sync_every)
        except ValueError as ve:
            raise ValueError(
                "SYNC_EVERY value is invalid. Try something like '2 minutes' or '1 hours'"
            ) from ve

    while True:
        if sync_every is None:
            next_run = None
        else:
            next_run = arrow.utcnow().dehumanize(sync_every)

        ICSToCalDAV(**settings).synchronise()

        if next_run is None:
            break
        else:
            seconds_to_next = (next_run - arrow.utcnow()).total_seconds()
            print(f'.next sync in {seconds_to_next}s')
            if seconds_to_next > 0:
                time.sleep(seconds_to_next)
