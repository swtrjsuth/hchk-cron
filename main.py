import urllib.request
import json
import os
import subprocess
import datetime
import time
import base64
import traceback

ENV_HCHECK_LOGIN_URL = os.getenv('HCHECK_LOGIN_URL')
ENV_HCHECK_LOGIN_USER = os.getenv('HCHECK_LOGIN_USER')
ENV_HCHECK_LOGIN_PASS = os.getenv('HCHECK_LOGIN_PASS')
ENV_HCHECK_API_URL = os.getenv('HCHECK_API_URL')
ENV_NOTIFY_URL = os.getenv('NOTIFY_URL')
ENV_WORKLOAD_LABELS_B64 = os.getenv('WORKLOAD_LABELS_B64')

try:
    workloadLabels = {}
    if ENV_WORKLOAD_LABELS_B64:
        try:
            wllabelsjson = base64.b64decode(ENV_WORKLOAD_LABELS_B64).decode('utf-8')
            workloadLabels = json.loads(wllabelsjson)
        except Exception as e:
            print('failed to parse ENV_WORKLOAD_LABELS_B64')
            pass

    # login
    payload = json.dumps({"returnSecureToken":True, "email":ENV_HCHECK_LOGIN_USER, "password":ENV_HCHECK_LOGIN_PASS})
    request = urllib.request.Request(
        ENV_HCHECK_LOGIN_URL,
        headers={'Content-Type':'application/json'},
        data=payload.encode('utf-8'),
        method="POST"
        )
    response = urllib.request.urlopen(request)
    response_text = response.read().decode('utf8')

    authdata = json.loads(response_text)

    idtoken = authdata["idToken"]

    # get healthcheck status
    request = urllib.request.Request(
        f'{ENV_HCHECK_API_URL}/workloads.json?auth={idtoken}',
        method="GET"
        )
    response = urllib.request.urlopen(request)
    response_text = response.read().decode('utf8')
    hb_status_data = json.loads(response_text)

    # get cached notifications

    process = subprocess.Popen(['curl','-s','-m', '4', f'{ENV_NOTIFY_URL}/json?since=all'], stdout=subprocess.PIPE)
    stdout = process.communicate()[0]
    jsonlines = stdout.decode('utf8')
    notify_events = []
    for l in jsonlines.split('\n'):
        tl = l.strip()
        if len(tl) > 0:
            notify_events.append(json.loads(tl))

    offline_notifications = {}
    online_notifications = {}

    for e in notify_events:
        e_title = e.get('title')
        e_message = e.get('message')
        if e_title and e_message:
            wlid = e_message.split(' ')[0].strip('[]')
            ntime = int(e.get('time'))
            existing_time = 0
            if e_title.startswith('OFFLINE '):
                try:
                    existing_time = int(offline_notifications.get(wlid))
                except:
                    pass
                offline_notifications[wlid] = ntime if ntime > existing_time else existing_time
            elif e_title.startswith('ONLINE ') and e_message:
                try:
                    existing_time = int(online_notifications.get(wlid))
                except:
                    pass
                online_notifications[wlid] = ntime if ntime > existing_time else existing_time

    pending_notifications = []

    # calculate online/offline statuses for hb servers
    tnow = int(time.time())
    workloads = hb_status_data
    for workloadID in workloads:
        workload = workloads.get(workloadID)
        if workload is None:
            continue
        muted = workload.get('m')
        if muted is not None and (muted == True or muted.lower() == 'true'):
            continue
        wlid = workloadID
        wlabel = workloadLabels.get(wlid)
        if wlabel is None:
            wlabel = workloadID
        tval = workload.get('t')
        if tval is None:
            continue
        last_hb_time = int(tval)
        expect_every_secs = int(workload['e']) * 60
        date_time = datetime.datetime.fromtimestamp( last_hb_time )
        off_n = offline_notifications.get(wlid)
        if last_hb_time + expect_every_secs < tnow:
            # notify OFFLINE
            if off_n is None or (off_n < last_hb_time):
                pending_notifications.append({'type':'offline','wlid':wlid,'wlabel':wlabel,'last':f'{date_time} UTC'})
        else:
            # notify ONLINE
            on_n = online_notifications.get(wlid)
            if off_n is not None and (off_n < last_hb_time) and (on_n is None or (on_n < off_n)):
                pending_notifications.append({'type':'online','wlid':wlid,'wlabel':wlabel,'last':f'{date_time} UTC'})

    for n in pending_notifications:
        payload = f'[{n["wlid"]}] is {n["type"]} as of {n["last"]}'
        tag = 'warning' if n["type"] == 'offline' else 'heavy_check_mark'
        request = urllib.request.Request(
            ENV_NOTIFY_URL,
            headers={'Title':f'{n["type"].upper()} {n["wlabel"]}', 'Tags': tag, 'Content-Type':'application/json'},
            data=payload.encode('utf-8'),
            method="POST"
            )
        response = urllib.request.urlopen(request)

    print(f'Sent {len(pending_notifications)} Notifications')

except Exception as e:
    etype = type(e)
    tb = traceback.format_exc()
    loc = tb.split('\n')[1].strip()
    print(f'{etype}, {loc}')
    exit(1)
