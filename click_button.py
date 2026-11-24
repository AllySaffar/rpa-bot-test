import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
SITE_URL = os.environ["SITE_URL"]
BOT_USERNAME = os.environ["BOT_USERNAME"]
BOT_PASSWORD = os.environ["BOT_PASSWORD"]

# ---------- SETTINGS: change these, not the code below ----------
TRAVEL_DATE = "Thursday, November 26,"   # exactly as the calendar shows it
FROM_SHORT = "mor"                       # what to type in the From box
FROM_STATION = "Morogoro"
TO_STATION = "Dar Es Salaam"
COACH = "9"
PREFERRED_SEAT = "71"
REFRESH_SECONDS = 300      # 5 minutes (must be shorter than the app's hold time)
MAX_RUN_MINUTES = 340      # stop after 5h40m (GitHub kills jobs at 6h)
HEADLESS = True            # True = invisible (GitHub). False = watch it on your laptop


def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def short(error):
    return str(error).splitlines()[0]


def login(page):
    page.goto(SITE_URL)
    page.get_by_text("Login").click()
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill(BOT_USERNAME)
    page.get_by_role("textbox", name="Email").press("Tab")
    page.get_by_role("textbox", name="Please Enter Password").fill(BOT_PASSWORD)
    page.get_by_role("button", name="Login").click()
    log("Logged in ✅")


def go_to_seat_page(page):
    page.locator("#indexFormDepartureDatePicker").click()
    page.get_by_role("gridcell", name=TRAVEL_DATE).click()
    page.locator("#indexFormDepartureStationSelect").get_by_role("combobox").click()
    page.locator("#indexFormDepartureStationSelect").get_by_role("combobox").fill(FROM_SHORT)
    page.get_by_role("option", name=FROM_STATION).click()
    page.locator("#indexFormArriveStationSelect").get_by_role("combobox").click()
    page.locator("#indexFormArriveStationSelect").get_by_role("combobox").click()
    page.get_by_role("option", name=TO_STATION).click()
    page.get_by_role("button", name="Search").click()
    page.get_by_role("button", name="railway car icon 10.Coach (").click()
    page.get_by_role("button", name=re.compile(rf"^{COACH} \.Coach")).click()
    page.locator("#ticketNavigationNextButton").click()
    page.wait_for_url("**/purchase/seat-selection")
    page.locator(".slot-box").first.wait_for()
    log("Arrived at seat selection ✅")


def pick_seat(page):
    free_seats = page.locator('.slot-box[title="Seat"]:not(.active)')
    count = free_seats.count()
    log(f"Free seats found: {count}")
    if count == 0:
        return None, None

    preferred = free_seats.filter(has=page.get_by_text(PREFERRED_SEAT, exact=True))
    if preferred.count() > 0:
        seat = preferred.first
    else:
        seat = free_seats.first
    number = seat.locator(".newSeat-index").inner_text().strip()

    all_texts = [t.strip() for t in page.locator(".slot-box").all_inner_texts()]
    my_seat = page.locator(".slot-box").nth(all_texts.index(number))
    my_seat.click()
    log(f"Holding seat {number} ✅")
    return my_seat, number


def fresh_round(page):
    page.goto(SITE_URL)
    go_to_seat_page(page)
    return pick_seat(page)


def recover(page):
    try:
        return fresh_round(page)
    except Exception as e:
        log(f"⚠️ Fresh round failed: {short(e)}. Logging in again...")
    try:
        login(page)
        return fresh_round(page)
    except Exception as e:
        log(f"❌ Recovery failed: {short(e)}. Will retry next cycle.")
        return None, None


def run(playwright):
    browser = playwright.chromium.launch(headless=HEADLESS)
    page = browser.new_page()
    start = time.time()
    login(page)
    my_seat, number = recover(page)

    while time.time() - start < MAX_RUN_MINUTES * 60:
        page.wait_for_timeout(REFRESH_SECONDS * 1000)
        try:
            if my_seat is None:
                raise Exception("no seat held right now")
            my_seat.click(timeout=10000)
            log(f"Released seat {number}")
            page.wait_for_timeout(3000)
            my_seat.click(timeout=10000)
            log(f"Holding seat {number} again ✅")
        except Exception as e:
            log(f"⚠️ Toggle failed: {short(e)}. Starting a fresh round...")
            my_seat, number = recover(page)

    log("⏰ Shift over. Releasing the seat for the next run.")
    if my_seat is not None:
        try:
            my_seat.click(timeout=10000)
            log(f"Released seat {number}. Bye 👋")
        except Exception as e:
            log(f"Couldn't release: {short(e)}")


with sync_playwright() as playwright:
    try:
        run(playwright)
    except KeyboardInterrupt:
        log("Bot stopped 👋")
