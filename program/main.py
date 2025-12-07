#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import socket
import fcntl
import struct


from datetime import datetime, date, timezone, timedelta
import time
import os.path

resdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'resources')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'waveshare-lib/RaspberryPi_JetsonNano/python/lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import logging
from waveshare_epd import epd7in3f
from PIL import Image,ImageDraw,ImageFont


# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Populated by values in resources/excludes.txt
EXCLUDE_LIST = []

print(f"libdir={libdir}")
print(f"resdir={resdir}")

logging.basicConfig(level=logging.INFO)

# Constants
originX = 20
originY = 20
maxX = 439  # max panel x is actually 479
maxY = 679  # max panel y is actually 799

# Calendar event
eventRectangleWidth = maxX-20
eventRectangleHeight = 45

# Left and right gutters. Right gutter is shown for all day events only
gutterWidth = 15
gutterHeight = 45

eventTimeOffsetX = 30   # From the startX of the eventRectangle
eventTimeOffsetY = 12   # From the startY of the eventRectangle

# one-line events
eventDescrOffsetX = 180  # From the startX of the eventRectangle
eventDescrOffsetY = 12    # From the startY of the eventRectangle

# first line of two-line events
eventDescrOneOffsetX = 180  # From the startX of the eventRectangle
eventDescrOneOffsetY = 2    # From the startY of the eventRectangle

# second line of two-line events
eventDescrTwoOffsetX = 180  # From the startX of the eventRectangle
eventDescrTwoOffsetY = 23    # From the startY of the eventRectangle

# Add this value to eventOriginY to get the next eventOriginY for the next day
dayHeaderHeight = 45

# Spacer between events, or between the day header and the first event under the day
eventSpacer = 10

# Add this value to eventOriginY to get the next eventOriginY for the next event
eventHeight = 45

# The number of characters allowed on the first line before a break is forced to the second line
eventCharLimit = 26

# Fonts
#eventFont = ImageFont.truetype(os.path.join(resdir, 'Font.ttc'), 18)
eventFont = ImageFont.truetype(os.path.join(resdir, 'FreeSansBold.ttf'), 18)
dayFont = ImageFont.truetype(os.path.join(resdir, 'FreeSans.ttf'), 23)
dayNumFont = ImageFont.truetype(os.path.join(resdir, 'FreeSans.ttf'), 40)

# Colors
epd_BLACK  = 0x000000   #   0000  BGR
epd_WHITE  = 0xffffff   #   0001
epd_GREEN  = 0x00ff00   #   0010
epd_BLUE   = 0xff0000   #   0011
epd_RED    = 0x0000ff   #   0100
epd_YELLOW = 0x00ffff   #   0101
epd_ORANGE = 0x0080ff   #   0110

# Reads the values in resources/color-map.txt to assign colors to the calendars
colorMap = {}

# Set to True to generate fake events. Useful if the Google calendar API is not available for some reason
makeFakeEvents = False


class PiCalendarEvent():
    def __init__(self, calendarName, eventSummary, allDayEventDate, eventStartTime, eventEndTime):
        self.calendarName = calendarName
        self.allDayEventDate = allDayEventDate
        self.eventSummary = eventSummary
        self.eventStartTime = eventStartTime
        self.eventEndTime = eventEndTime

    def get_sort_key(self):
        """
        Returns a tuple for sorting:
        - Primary: the date (from either allDayEventDate or eventStartTime)
        - Secondary: 0 for all-day events, 1 for timed events (so all-day comes first)
        - Tertiary: time of day for timed events (midnight for all-day)
        """
        if self.allDayEventDate:
            # All-day event: use the date, sort before timed events (0), time is midnight
            return (self.allDayEventDate, 0, datetime.min.time())
        elif self.eventStartTime:
            # Timed event: extract date and time
            return (self.eventStartTime.date(), 1, self.eventStartTime.time())
        else:
            # No date info - sort these last
            return (date.max, 2, datetime.max.time())

    # Gets the event date as a datetime string without the time component
    def getDateNoTimeStr(self):
        if self.allDayEventDate:
            return self.allDayEventDate.strftime("%Y-%m-%d")
        else:
          return self.eventStartTime.strftime("%Y-%m-%d")

# Takes in a date object and returns "Today", "Tomorrow", or the weekday
def formatEventWeekday(eventDate):
    weekdays = {}
    weekdays[0] = "Monday"
    weekdays[1] = "Tuesday"
    weekdays[2] = "Wednesday"
    weekdays[3] = "Thursday"
    weekdays[4] = "Friday"
    weekdays[5] = "Saturday"
    weekdays[6] = "Sunday"

    today = datetime.now()
    tomorrow = datetime.now() + timedelta(days=1)

    if today.day == eventDate.day:
        return "Today"
    elif tomorrow.day == eventDate.day:
        return "Tomorrow"
    else:
        return weekdays[eventDate.weekday()]

def formatEventDateTime(eventDate):
    amPm = "AM"
    eventHour = eventDate.hour
    eventMinute = eventDate.minute

    if eventHour == 0:
        eventHour = 12
    elif eventHour == 12:
        amPm = "PM"
    elif eventHour > 12:
        eventHour = eventHour - 12
        amPm = "PM"

    hourMinuteSeparator = ":"
    eventMinuteStr = eventDate.strftime("%M")

    if eventMinute == 0:
        hourMinuteSeparator = ""
        eventMinuteStr = ""

    return f"{eventHour}{hourMinuteSeparator}{eventMinuteStr}{amPm}"

def getRealEvents():
    piEvents = []

    # Get the current local time information
    localTimeInfo = time.localtime()
    isDst = localTimeInfo.tm_isdst

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    tokenFile = os.path.join(resdir, "token.json")
    credentialsFile = os.path.join(resdir, "credentials.json")

    if os.path.exists(tokenFile):
      creds = Credentials.from_authorized_user_file(tokenFile, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentialsFile, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(tokenFile, "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)

        # Call the Calendar API
        now = datetime.now(tz=timezone.utc).isoformat()

        calendars_result = service.calendarList().list().execute()
        calendars = calendars_result.get("items", [])

        if not calendars:
            print("No calendars found")
            return


        for calendar in calendars:
            calendarName = calendar["summary"]
            if calendarName in EXCLUDE_LIST:
                continue

            logging.debug("\nCalendar id=%s, summary=%s\n------------" % (calendar["id"], calendarName))
            calendarTimeZone = calendar["timeZone"]

            events_result = service.events().list(calendarId=calendar["id"],
              timeMin=now,
              maxResults=10,
              singleEvents=True,
              orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])

            if not events:
                print("No upcoming events found.")
            else:
                for event in events:
                    logging.debug(f"event={str(event)}")
                    startDateTimeStr = event["start"].get("dateTime")
                    endDateTimeStr = event["end"].get("dateTime")

                    allDay = None
                    startDateTime = None
                    endDateTime = None
                    if startDateTimeStr is None:
                        allDay = datetime.fromisoformat(event["start"].get("date"))
                        allDay = allDay.date()
                    else:
                        startDateTime = datetime.fromisoformat(startDateTimeStr)
                        endDateTime = datetime.fromisoformat(endDateTimeStr)

                        # Handle when a calendar's time zone was set to UTC for some reason. All the events on the
                        # calendar have to be adjusted.
                        if calendarTimeZone == "UTC":
                            if isDst:
                                startDateTime = startDateTime + timedelta(hours=-7)
                                endDateTime = endDateTime + timedelta(hour=-7)
                            else:
                                startDateTime = startDateTime + timedelta(hours=-8)
                                endDateTime = endDateTime + timedelta(hours=-8)

                    piEvent = PiCalendarEvent(calendarName = calendar["summary"],
                                                eventSummary = event["summary"],
                                                allDayEventDate = allDay,
                                                eventStartTime= startDateTime,
                                                eventEndTime = endDateTime)

                    piEvents.append(piEvent)
    except HttpError as error:
        print(f"An HTTP occurred: {error}")
        exit(1)

    return piEvents

def generateFakeEvents():
    piEvents = []

    ## First day
    # First event
    allDay = date.today()
    now = datetime.now()

    piEvent = PiCalendarEvent(calendarName="RED-CALENDAR",
                              eventSummary="Cat's birthday",
                              allDayEventDate=allDay,
                              eventStartTime = None,
                              eventEndTime = None)

    piEvents.append(piEvent)

    # Second event
    eventStart = now.replace(hour=8, minute=0)
    eventEnd = now.replace(hour=9, minute=30)

    piEvent = PiCalendarEvent(calendarName="GREEN-CALENDAR",
                            eventSummary="Conference call",
                            allDayEventDate=None,
                            eventStartTime = eventStart,
                            eventEndTime = eventEnd)

    piEvents.append(piEvent)

    # Third event
    eventStart = now.replace(hour=9, minute=30)
    eventEnd = now.replace(hour=10, minute=0)

    piEvent = PiCalendarEvent(calendarName="BLUE-CALENDAR",
                            eventSummary="Try to remember conference call decision",
                            allDayEventDate=None,
                            eventStartTime = eventStart,
                            eventEndTime = eventEnd)

    piEvents.append(piEvent)

    ## Second day. Increment days = 1
    # First event
    allDay = date.today() + timedelta(days=1)

    piEvent = PiCalendarEvent(calendarName="YELLOW-CALENDAR",
                            eventSummary="Unspecified school holiday",
                            allDayEventDate=allDay,
                            eventStartTime = None,
                            eventEndTime = None)

    piEvents.append(piEvent)

    # Second event
    eventStart = (now + timedelta(days=1)).replace(hour=14, minute=0)
    eventEnd = (now + timedelta(days=1)).replace(hour=16, minute=30)

    piEvent = PiCalendarEvent(calendarName="BLUE-CALENDAR",
                            eventSummary="'Design' session at pub",
                            allDayEventDate=None,
                            eventStartTime = eventStart,
                            eventEndTime = eventEnd)

    piEvents.append(piEvent)

    ## Third day - no events. Increment days = 2

    ## Fourth day. Increment days = 3
    # First event
    eventStart = (now + timedelta(days=3)).replace(hour=11, minute=30)
    eventEnd = (now + timedelta(days=3)).replace(hour=12, minute=30)

    piEvent = PiCalendarEvent(calendarName="ORANGE-CALENDAR",
                            eventSummary="Lunch with Larry Linder",
                            allDayEventDate=None,
                            eventStartTime = eventStart,
                            eventEndTime = eventEnd)

    piEvents.append(piEvent)

    ## Fifth day. Increment days = 4.
    # First event "All day", "Holiday"
    allDay = date.today() + timedelta(days=4)

    piEvent = PiCalendarEvent(calendarName="YELLOW-CALENDAR",
                        eventSummary="Holiday",
                        allDayEventDate=allDay,
                        eventStartTime = None,
                        eventEndTime = None)

    piEvents.append(piEvent)
    return piEvents

def drawDayHeader(draw, dayNumText, dayText, eventOriginX, eventOriginY):
    # Current day number
    draw.text((eventOriginX, eventOriginY-10), dayNumText, font = dayNumFont, fill = epd_BLACK)

    # Current day
    draw.text((eventOriginX+70, eventOriginY+2), dayText, font = dayFont, fill = epd_BLACK)

    # Horizontal line between the day text and the first event
    draw.line((eventOriginX, eventOriginY+35, maxX, eventOriginY+35), width = 2, fill = epd_BLACK)

def drawEvent(draw, eventOriginX, eventOriginY, color, timeText, line1Text, line2Text):
    # large event rectangle. 440 wide by 45 high
    draw.rounded_rectangle((eventOriginX, eventOriginY+45, maxX, eventOriginY+90), fill=color, outline=color, width=2, \
corners=((eventOriginX,eventOriginY+45), (maxX, eventOriginY+45), (eventOriginX, eventOriginY+90), (maxX, eventOriginY+90)), radius=8)

    textColor = epd_WHITE
    if color == epd_YELLOW or color == epd_ORANGE:
        textColor = epd_BLACK

    # event time
    draw.text((eventOriginX+25, eventOriginY+60), timeText, font = eventFont, fill = textColor)

    if line2Text is not None:
        # event description
        draw.text((eventOriginX+190, eventOriginY+50), line1Text, font = eventFont, fill = textColor)

        # event description 2
        draw.text((eventOriginX+190, eventOriginY+70), line2Text, font = eventFont, fill = textColor)
    else:
        draw.text((eventOriginX+190, eventOriginY+60), line1Text, font = eventFont, fill = textColor)

def drawNoEvents(draw, eventOriginX, eventOriginY):
    draw.text((eventOriginX+30, eventOriginY+60), "No events", font = eventFont, fill = epd_BLACK)

def maybeSplitEventSummary(eventSummary):
    parts = eventSummary.split()

    truncatedMsg = ""
    truncatedMsg2 = ""
    useTruncated2 = False

    for word in parts:
        if (len(truncatedMsg) + len(word) + 1) > eventCharLimit:
            useTruncated2 = True

        if useTruncated2:
            truncatedMsg2 += f"{word} "
        else:
            truncatedMsg += f"{word} "

    truncatedMsg = truncatedMsg.strip()
    truncatedMsg2 = truncatedMsg2.strip()

    return [truncatedMsg, truncatedMsg2]

def sortEvents(piEvents):
    sortedEvents = sorted(piEvents, key=lambda e: e.get_sort_key())

    eventsByDay = {}
    for event in sortedEvents:
        dateStr = event.getDateNoTimeStr()
        dailyEvents = None

        if dateStr in eventsByDay:
            dailyEvents = eventsByDay[dateStr]
        else:
            dailyEvents = []

        dailyEvents.append(event)
        eventsByDay[dateStr] = dailyEvents

    return eventsByDay

def drawEvents(draw, eventsByDay, eventOriginX, eventOriginY):
    now = datetime.now()
    for i in range(0, 10):
        # First, calculate where there is enough room for both the header and 1 event
        proposedHeight = eventOriginY + dayHeaderHeight + eventSpacer + eventHeight + eventSpacer
        logging.debug(f"Processing day {i}")
        logging.debug(f"eventOriginY={eventOriginY}, dayHeaderHeight={dayHeaderHeight}, eventSpacer={eventSpacer}, eventHeight={eventHeight}, proposedHeight={proposedHeight}. maxY={maxY}")
        if proposedHeight > maxY:
            logging.debug("No more room for header + an event, exiting now")
            return

        currentDay = (now + timedelta(days=i))
        currentDayStr = currentDay.strftime("%Y-%m-%d")

        drawDayHeader(draw, str(currentDay.day), formatEventWeekday(currentDay), eventOriginX, eventOriginY)

        logging.info(f"\n{currentDay.day}    {formatEventWeekday(currentDay)}")
        logging.info("--------------------------------------------------------------------")

        if currentDayStr in eventsByDay:
            dailyEvents = eventsByDay[currentDayStr]

            for event in dailyEvents:
                # Calculate where there is enough room for another event
                logging.debug(f"Processing event {event.eventSummary} on day {event.getDateNoTimeStr()}")
                proposedHeight = eventOriginY + eventSpacer + eventHeight + eventSpacer
                logging.debug(f"eventOriginY={eventOriginY}, eventSpacer={eventSpacer}, proposedHeight={proposedHeight}. maxY={maxY}\n")
                if proposedHeight > maxY:
                    logging.debug("No more room for any more events, exiting now")
                    return

                summaryTruncated = maybeSplitEventSummary(event.eventSummary)
                summaryFirstLine = summaryTruncated[0]
                summarySecondLine = None

                if (len(summaryTruncated[1]) > 0):
                    summarySecondLine = summaryTruncated[1]

                color = colorMap.get(event.calendarName, epd_BLACK)
                if event.allDayEventDate:
                    drawEvent(draw, eventOriginX, eventOriginY, color, "All day", summaryFirstLine, summarySecondLine)
                    logging.info(f"All day - {event.eventSummary}, color={color}")
                else:
                    timeStr = f"{formatEventDateTime(event.eventStartTime)} - {formatEventDateTime(event.eventEndTime)}"
                    drawEvent(draw, eventOriginX, eventOriginY, color, timeStr, summaryFirstLine, summarySecondLine)
                    logging.info(f"{formatEventDateTime(event.eventStartTime)} - {formatEventDateTime(event.eventEndTime)} {event.eventSummary}, color={color}")

                eventOriginY = eventOriginY + eventHeight + eventSpacer

        else:
            drawNoEvents(draw, eventOriginX, eventOriginY)
            logging.info("No events")
            eventOriginY = eventOriginY + eventHeight + eventSpacer


        eventOriginY = eventOriginY + dayHeaderHeight + eventSpacer

def get_interface_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15].encode('utf-8'))
    )[20:24])


def loadDrawCalendars(draw, originX, originY):
    piEvents = []

    if makeFakeEvents:
        piEvents = generateFakeEvents()
    else:
        piEvents = getRealEvents()

    # Sort all the events by date and then by time. All day events are sorted first in each day
    eventsByDay = sortEvents(piEvents)

    # Process events for the next 10 days
    drawEvents(draw, eventsByDay, originX, originY)
    logging.debug("All events have been drawn")

    updatedFont = ImageFont.truetype(os.path.join(resdir, 'Font.ttc'), 16)
    now = datetime.now()
    lastUpdated = f"Last updated: {now.strftime("%m/%d %H:%M")}"
    draw.text((originX , maxY+5), lastUpdated, font = updatedFont, fill = epd_BLACK)

    ipAddr = get_interface_ip_address('wlan0')
    draw.text((originX + 250, maxY+5), ipAddr, font = updatedFont, fill = epd_GREEN)

def main():
    colorFilePath = os.path.join(resdir, 'color-map.txt')
    try:
        with open(colorFilePath, "r") as colorFile:
            for line in colorFile:
                line = line.strip()
                parts = line.split("=")

                calendarName = parts[0]
                colorStr = parts[1]
                color = None

                if "yellow" == colorStr:
                    color = epd_YELLOW
                elif "orange" == colorStr:
                    color = epd_ORANGE
                elif "red" == colorStr:
                    color = epd_RED
                elif "green" == colorStr:
                    color = epd_GREEN
                elif "blue" == colorStr:
                    color = epd_BLUE
                elif "white" == colorStr:
                    color = epd_WHITE
                else:
                    color = epd_BLACK

                colorMap[parts[0]] = color

    except FileNotFoundError:
        print(f"Error: The file {colorFilePath} was not found.")
        exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)

    excludeFilePath = os.path.join(resdir, 'excludes.txt')
    try:
        with open(excludeFilePath, "r") as excludeFile:
            for line in excludeFile:
                line = line.strip()
                EXCLUDE_LIST.append(line)

    except FileNotFoundError:
        print(f"Error: The file {colorFilePath} was not found.")
        exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)

    try:
        epd = epd7in3f.EPD()
        logging.debug("Clearing screen...")
        epd.init()

        logging.debug("Clear complete")

        # https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html
        # Draw on the Image. Use (epd.width, epd.height) for landscape mode. Use (epd.height, epd.width) for portrait mode.
        # In portrait mode, width = 480, height = 800. (0, 0) is at the top left of the image.
        Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)  # 255: clear the frame
        draw = ImageDraw.Draw(Himage)

        loadDrawCalendars(draw, originX, originY)

        epd.display(epd.getbuffer(Himage))
        epd.sleep()

    except IOError as e:
        logging.info(e)

    except KeyboardInterrupt:
        logging.info("ctrl + c:")
        epd7in3f.epdconfig.module_exit(cleanup=True)
        exit()

if __name__ == "__main__":
    main()
