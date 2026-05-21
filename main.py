import datetime
import json
import os
import pytz

import functions_framework
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from signalwire.rest import Client as signalwire_client

# Define the scopes needed for Google Calendar access
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def load_credentials():
    """
    Loads Google Cloud credentials using Application Default Credentials (ADC).
    Falls back to a local creds.json file if available.
    """
    custom_creds = os.environ.get("SERVICE_ACCOUNT_FILE", "creds.json")
    
    # If a local custom creds file exists and GOOGLE_APPLICATION_CREDENTIALS is not set,
    # set it automatically for local testing convenience.
    if os.path.exists(custom_creds) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = custom_creds
        print(f"Local environment: Setting GOOGLE_APPLICATION_CREDENTIALS to {custom_creds}")

    try:
        # standard Google ADC loading (works natively inside GCP)
        credentials, project = google.auth.default(scopes=SCOPES)
        return credentials
    except Exception as e:
        print(f"Application Default Credentials not found or invalid: {e}")
        # Fallback to direct service account file loading
        if os.path.exists(custom_creds):
            print(f"Fallback: Loading credentials from local file '{custom_creds}'")
            return service_account.Credentials.from_service_account_file(custom_creds, scopes=SCOPES)
        raise RuntimeError(
            "Could not load Google credentials. Please configure Application Default Credentials "
            f"or place a valid '{custom_creds}' file in the root directory."
        ) from e

def build_calendar_service(credentials):
    """Builds and returns the Google Calendar API service client."""
    return build('calendar', 'v3', credentials=credentials)

def load_unit_list():
    """
    Loads the unit recipient list mapping units to phone numbers.
    Tries to load from the 'UNIT_LIST_JSON' environment variable,
    and falls back to reading a local 'units.json' file.
    """
    # 1. Try to load from UNIT_LIST_JSON environment variable
    unit_list_json = os.environ.get("UNIT_LIST_JSON")
    if unit_list_json:
        try:
            return json.loads(unit_list_json)
        except Exception as e:
            print(f"Error parsing UNIT_LIST_JSON with json.loads: {e}")
            try:
                import ast
                parsed_list = ast.literal_eval(unit_list_json)
                print("Successfully parsed UNIT_LIST_JSON using ast.literal_eval (Python dict format).")
                return parsed_list
            except Exception as e2:
                print(f"Error parsing UNIT_LIST_JSON with ast.literal_eval: {e2}")
    
    # 2. Try to load from units.json file (default or configured via UNIT_LIST_FILE)
    unit_list_file = os.environ.get("UNIT_LIST_FILE", "units.json")
    if os.path.exists(unit_list_file):
        try:
            with open(unit_list_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading unit list file '{unit_list_file}': {e}")
            
    print("Warning: No unit list configured. No notifications will be sent.")
    return {}

def get_tomorrow_time_range():
    """Returns the ISO formatted start and end times for tomorrow in US/Eastern timezone."""
    eastern = pytz.timezone('US/Eastern')
    now_utc = datetime.datetime.now(pytz.utc)
    now_eastern = now_utc.astimezone(eastern)
    today = now_eastern.date()
    tomorrow = today + datetime.timedelta(days=1)
    
    # Tomorrow morning 6:00 AM Eastern to end of day tomorrow
    start_of_tomorrow = datetime.datetime.combine(tomorrow, datetime.time(hour=6)).isoformat() + 'Z'
    end_of_tomorrow = datetime.datetime.combine(tomorrow, datetime.time.max).isoformat() + 'Z'
    return start_of_tomorrow, end_of_tomorrow

def get_events_for_tomorrow(service, start, end):
    """Fetches events from the configured Google Calendar for the tomorrow time range."""
    calendar_id = os.environ.get("CALENDAR_ID")
    if not calendar_id:
        print("Error: CALENDAR_ID environment variable is not configured.")
        return []
    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except Exception as e:
        print(f"Error fetching events from Google Calendar '{calendar_id}': {e}")
        return []

def get_garbage_info(events):
    """Parses events to extract unit number and pickup waste type information."""
    unit_number = ''
    garbage_type = ''
    for event in events:
        summary = event.get('summary', '')
        if "Unit" in summary:
            unit_number = summary
        elif "Pickup" in summary:
            garbage_type = summary.replace("Pickup - ", "")
    return unit_number, garbage_type

def send_message(body, phone_number):
    """Sends an SMS message using SignalWire REST API."""
    project_id = os.environ.get("SIGNALWIRE_PROJECT_ID")
    token = os.environ.get("SIGNALWIRE_TOKEN")
    space_url = os.environ.get("SIGNALWIRE_SPACE_URL")
    from_number = os.environ.get("SIGNALWIRE_FROM_NUMBER")
    
    if not all([project_id, token, space_url, from_number]):
        missing = [k for k, v in {
            "SIGNALWIRE_PROJECT_ID": project_id,
            "SIGNALWIRE_TOKEN": token,
            "SIGNALWIRE_SPACE_URL": space_url,
            "SIGNALWIRE_FROM_NUMBER": from_number
        }.items() if not v]
        raise ValueError(f"Missing required SignalWire configuration environment variables: {', '.join(missing)}")
        
    client = signalwire_client(project_id, token, signalwire_space_url=space_url)
    message = client.messages.create(
        from_=from_number,
        to=phone_number,
        body=body
    )
    return message.sid

@functions_framework.http
def main(request):
    """HTTP Cloud Function endpoint that coordinates calendar checks and sends SMS notifications."""
    calendar_id = os.environ.get("CALENDAR_ID")
    if not calendar_id:
        return "Error: CALENDAR_ID environment variable is not set.", 500
        
    try:
        credentials = load_credentials()
        service = build_calendar_service(credentials)
    except Exception as e:
        return f"Authentication Error: {e}", 500
        
    start, end = get_tomorrow_time_range()
    events = get_events_for_tomorrow(service, start, end)

    if not events:
        return "No events found for tomorrow."

    unit_number = None
    garbage_type = None

    for event in events:
        event_unit_number, event_garbage_type = get_garbage_info([event])
        if event_unit_number:
            unit_number = event_unit_number
        if event_garbage_type:
            garbage_type = event_garbage_type

    message_sids = []
    
    if unit_number is not None and garbage_type is not None:
        message = f"Reminder {unit_number}! Waste Connections will pickup {garbage_type.lower()} tomorrow."
        unit_list = load_unit_list()
        phone_numbers = unit_list.get(unit_number, [])
        
        if not phone_numbers:
            print(f"Warning: No phone numbers configured for unit '{unit_number}'.")
            return f"No phone numbers configured for unit: {unit_number}"
            
        for number in phone_numbers:
            try:
                sid = send_message(message, number)
                message_sids.append(sid)
            except Exception as e:
                print(f"Failed to send SMS to {number}: {e}")
                
        return {"status": "success", "message_sids": message_sids}
    else:
        return "No garbage pickup events found for tomorrow."