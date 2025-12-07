# pi-calendar3
Installation instructions and source code for getting an e-ink event calendar running for a Raspberry Pi

# Parts list
- Waveshare ACeP 7-Color E-Paper E-Ink Display + ePaper HAT for Raspberry Pi
https://www.waveshare.com/7.3inch-e-paper-hat-f.htm

- Raspberry Pi. A Pi 3 and and Pi Zero both worked with the e-ink display, but the Zero does not support remote development via VSCode.

- Micro-USB cable

- Standard 6x8 picture frame matted to 4x6. The e-ink display is slightly larger than 4x6 so you need a bit of extra room.

# Testing the display
You can test the e-ink display using the library functions provided by Waveshare. This is a good start to make sure the e-ink display functions at all. See https://github.com/waveshareteam/e-Paper You can download the whole repository, but you only really need to care about the files in the `RaspberryPi_JetsonNano/python` folder. Within this folder is an `examples` folder. You can run `epd_7in3e_test.py`, `epd_7in3f_test.py` or `epd_7in3g_test.py`. They all use different images in their tests. Be aware that these programs run *very* slowly, due to the fact that the e-ink display takes so long to refresh. Expect the screen to flash 30+ times in different colors when running these programs. Also, the programs take a full minute to execute and show images.

# Installation
To use the correct google auth Python libraries and e-ink Python libraries on a Pi, you are required to set up a Python virtual environment and use 'pip' within that environment to install the libraries. This is needed since the 2023 Bookworm release of Raspberry Pi OS can no longer run `sudo pip` natively to globally install Python packages. 

## Create Python virtual environment
python3 -m venv --system-site-packages python-virtual-env

## Activate Python virtual environment
source python-virtual-env/bin/activate

## Install needed google auth libraries. Do this after activating the Python virtual environment using 'source python-virtual-env/bin/activate'
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

## Install Pillow image library
pip install Pillow

## Install Jetson for Waveshare stuff
pip install Jetson.GPIO

## Unactivate Python virtual environment after everything is installed
deactivate

# Configuration
The e-ink calendar listed above can display the following colors: yellow, orange, red, green, blue and black. Entries for each calendar can be assigned one of these colors. To assign a color to a calendar, open `resources/color-map.txt`. This file has a series of key/value pairs. The key is the text of the calendar summary, such as 'Holidays in United States'. The value is the color that should be assigned to entries under that calendar.

# Execution
Simply run `programs/main.sh` to execute main.py in the python virtual environment. When everything is set up correctly, this will grab the calendar entries from the Google Calendar Api endpoint, make PiCalendarEvent object from the entries, and then populate the calendar with the entries. The code will stop populating the calendar when there is no longer enough room to add entries. if you want to see the calendar in action without calling the Google Calendar Api, read the "Fake events" section below.

# Fake events
The main.py program can create fake events for testing without displaying personally identifiable calendar information. This mode also avoids the Google Calendar API calls, so you can get the calendar display running then circle back to the calendar authentication later. Within main.py, set makeFakeEvents = True. Then run main.sh to populate the calendar with the fake events. 

# Google Calendar Authentication
In order to display real calendar events, main.py needs to be able to authenticate against the Google Calendar API. This is the hardest part of getting all this working. Your best best is to start at https://developers.google.com/workspace/calendar/api/quickstart/python and follow all the steps. OAuth stuff is discussed here: https://developers.google.com/workspace/guides/configure-oauth-consent At some point, it should ask you to save a `credentials.json` file. Save this file to the `resources` folder. When running main.py for the first time, the program should open a local web browser that should redirect to the Google login page. You then have to use your Google credentials to log in. This *should* save a `token.json` in the resources folder (although it may save the token.json file somewhere else). Once `credentials.json` and `token.json` are in place in the `resources` folder, running main.py should use these files to automatically download calendar events.

## Exclude calendars
By default, main.py will display entries for all calendars that it receives from the Google Calendar API. Because of the way the API works, the program first queries the calendar API for a full list of calendar ids. Then it calls the calendar API again for each calendar id to receive events for each calendar. If you have calendars that you know that you never want to display, you can add the calendars to `resources/excludes.txt`. This file is a list of calendar summaries. To exclude a calendar, copy the calendar's summary text into its own line in this file and save. Now the program will never query for events for that calendar.