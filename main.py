import urllib.request
import json
import os
import subprocess
import datetime

'''
HCHECK_API_URL=https://healthcheckserver:1234
HCHECK_API_KEY=12345678-1234-abcd-efff-816544e29bc0
NOTIFY_URL=https://notificationserver:8080/topicname
'''

ENV_HCHECK_API_URL = os.getenv('HCHECK_API_URL')
ENV_HCHECK_API_KEY = os.getenv('HCHECK_API_KEY')
ENV_NOTIFY_URL = os.getenv('NOTIFY_URL')

try:
    # get healthcheck status

    request = urllib.request.Request(
        f'{ENV_HCHECK_API_URL}/status',
        headers={'Authorization':f'token {ENV_HCHECK_API_KEY}', 'Content-Type':'application/json'},
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
            wlid = e_message[1:37]
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
    tnow = int(hb_status_data['tnow'])
    workloads = hb_status_data['workloads']
    for workload in workloads:
        if workload.get('muted'):
            continue
        wlid = workload['workload_id']
        wlabel = workload['label']
        last_hb_time = int(workload['last_hb_time'])
        expect_every_secs = int(workload['expect_every']) * 60
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
        payload = f'[{n["wlid"]}] is {n["type"]} as of {n["last"]})'
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
    print(e)
    exit(1)
