from datetime import datetime, timedelta
import requests
import time
import re
import sys
import time
from twocaptcha import TwoCaptcha

TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = 1

TEMP_MAIL_ENDPOINT = ''

UKVCAS_USERNAME = ''
UKVCAS_PASSWORD = ''

POST_CODE = ''

RUCAPTCHA_API_KEY = ''


AUTH_TOKEN = ''
APP_CASE = ''
API_ROOT = 'https://api.ukvcas.co.uk/api/v1'
DEFAULT_HEADERS = {
    'User-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36',
}
RETURN_URL = '/connect/authorize/callback?client_id=Visa%20Application&redirect_uri=https%3A%2F%2Fwww.ukvcas.co.uk%2Fcallback&response_type=id_token%20token&scope=openid%20profile%20FES_Internal&state=_&nonce=_'



s = requests.Session()

def exit():
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": "Bot failed, sorry..."}
    )
    sys.exit(1)

def get_passcode():
    time.sleep(30)
    r = requests.get(TEMP_MAIL_ENDPOINT)
    m = re.search(r'Use this Access Code (\d+)', r.text)
    return m.group(1)

def get_form_data(text):
    data = {}
    m = re.search(r'name="__RequestVerificationToken" type="hidden" value="(.*?)"', text)
    data['__RequestVerificationToken'] = m.group(1)
    data['BlockResetPassword'] = 'False'
    data['button'] = 'login'

    matches = re.finditer(r'name="(PageNo|Username|Password)" value="(.*?)"', text)
    data.update({m.group(1): m.group(2) for m in matches if m.group(2)})

    m = re.search(r'render=(.*?)"', text)
    google_key = m.group(1)

    solver = TwoCaptcha(RUCAPTCHA_API_KEY)
    try:
        re_captcha_result = solver.recaptcha(
            sitekey=google_key,
            url='https://auth.ukvcas.co.uk/Account/Login',
            version='v3',
            score=0.5
        )

    except Exception as e:
        exit()

    data['ReCaptcha'] = re_captcha_result['code']
    return data

def get_auth_token():
    r = s.get('https://auth.ukvcas.co.uk/Account/Login', params={
        'ReturnUrl': RETURN_URL,
        }, headers=DEFAULT_HEADERS)

    data = get_form_data(r.text)
    data.update({
            'ReturnUrl': RETURN_URL,
            'Username':  UKVCAS_USERNAME,
            'Password':  UKVCAS_PASSWORD,
        })


    r = s.post('https://auth.ukvcas.co.uk/Account/Login',
                        params={
                            'ReturnUrl': RETURN_URL
                        },
                        data=data,
                        headers=DEFAULT_HEADERS
                     )

    data = get_form_data(r.text)
    data['Passcode'] = get_passcode()


    r = s.post('https://auth.ukvcas.co.uk/Account/Login',
                        params={
                            'ReturnUrl': RETURN_URL
                        },
                        data=data,
                        headers=DEFAULT_HEADERS
                     )

    m = re.search(r'access_token=(.*?)&', r.url)
    return m.group(1)

print("# Initial Auth...")
try:
    AUTH_TOKEN = get_auth_token()
except:
    exit()

auth_time = time.time()

# Load appointment centers
r = requests.get(
        '%s/ServicePoint/NearestDetails/' % API_ROOT,
        headers={
            'authorization': 'Bearer %s' % AUTH_TOKEN
        },
        params={
            'location': POST_CODE
        }
    )

delta = timedelta(days=7)
service_points = r.json()['servicePoints']
service_point_dates = {}

while True:
    today = datetime.now() + timedelta(days=1)
    hard_limit = today + timedelta(days=60)

    if (time.time() - auth_time) > 3000:
        print("# Refreshing token...")
        try:
            AUTH_TOKEN = get_auth_token()
        except:
            exit()

        auth_time = time.time()

    notifications = []
    print("#Starting new cycle")
    
    send_notification = False
    for service_point in service_points:
        service_point_id = service_point['id']

        if service_point_id not in service_point_dates:
            service_point_dates[service_point_id] = None

        service_point_name = service_point['name']
        dt = today
        print(f"Parsing {service_point_name}...")
        while dt < hard_limit:

            r = requests.get(
                f'{API_ROOT}/ServicePoint/{service_point_id}/Case/{APP_CASE}/Availability',
                headers={
                    'authorization': 'Bearer %s' % AUTH_TOKEN
                },
                params={
                    'apptDate': f'{dt:%Y-%m-%d}',
                    'daysAhead': '6'
                }
            )

            dt += delta

            try:
                appointments = r.json()
            except:
                print(r.text)

            appointemnts_found = False
            if 'errors' in appointments:
                break

            if 'standard' in appointments and appointments['standard']:
                for appointment in appointments['standard']:
                    appointment_date = datetime.strptime(appointment['date'], "%Y-%m-%d")
                    if appointment['slots'] is None:
                        continue

                    if service_point_dates[service_point_id] is None or appointment_date < service_point_dates[service_point_id]:
                        service_point_dates[service_point_id] = appointment_date
                        send_notification = True

                    appointemnts_found = True
                    notifications += [{'dt': appointment_date, 'type': 'standard', 'service_point_name': service_point_name}]
                    break

            if 'express' in appointments and appointments['express']:
                for appointment in appointments['express']:
                    appointment_date = datetime.strptime(appointment['date'], "%Y-%m-%d")
                    if appointment['slots'] is None:
                        continue

                    if service_point_dates[service_point_id] is None or appointment_date < service_point_dates[service_point_id]:
                        service_point_dates[service_point_id] = appointment_date
                        send_notification = True

                    appointemnts_found = True
                    notifications += [{'dt': appointment_date, 'type': 'express', 'service_point_name': service_point_name}]
                    break

    notification_text = "Found new appointment slots:\n"

    if send_notification:
        for notification in sorted(notifications, key=lambda x: x['dt']):
            notification_text += f"{notification['dt']:%Y-%m-%d} {notification['type']} {notification['service_point_name']}\n"

        requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": notification_text}
            )
        print(notification_text)

    print("#Done, going to sleep")
    time.sleep(30)

