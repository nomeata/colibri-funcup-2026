#!/usr/bin/env python3

# Generates the website

import json
import os
import jinja2
import math
import shutil
import datetime
import re
import numpy as np
import pandas as pd
import folium
import csv

import constants

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

hike_and_fly_re = re.compile(r'\bhike\b', re.IGNORECASE)

from jinja2 import Environment, FileSystemLoader, select_autoescape
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

def full_name(f):
    return f['FirstName'] + ' ' + f['LastName']

def pretty_duration(s):
    s = int(s)
    if s < 60:
        return f"{s}s"
    elif s < 60*60:
        return f"{math.floor(s/60)} min"
    else:
        return f"{math.floor(s/(60*60))} h {math.floor((s % (60*60))/60)} min"

def pretty_landepunktabstand(d):
    if d < 200:
        return f"{d} m"
    else:
        return ""

# prepare output directory

try:
    os.mkdir('_out')
except FileExistsError:
    pass
shutil.copytree('templates/static', '_out/static', dirs_exist_ok=True)

flight_data = json.load(open('_tmp/flights.json'))

flights = {}
# Group flights by pilot, read stats
for flight in flight_data:
    id = flight['IDFlight']
    pid = str(flight['FKPilot'])

    # add stats
    #print(f"Reading stats for {id}")
    flight['stats'] = json.load(open(f'_stats/{id}.stats.json'))

    if pid not in flights:
        flights[pid] = []
    flights[pid].append(flight)

# Sort by date
for pid, pflights in flights.items():
    pflights.sort(key = lambda f: f['FlightStartTime'])

# Latest flight
if flight_data:
    latest_flight = max([f['FlightStartTime'] for f in flight_data])
else:
    latest_flight = "(noch keinen gesehen)"

# derived and cleand-up stats
for flight in flight_data:
    flight['stats']['drehueberschuss'] = abs(flight['stats']['left_turns'] - flight['stats']['right_turns'])
    flight['stats']['duration'] = flight['FlightDuration']
    flight['stats']['maxalt'] = flight['MaxAltitude']
    time_str = flight['FlightStartTime'].split(' ')[1]
    time_obj = datetime.datetime.strptime(time_str, "%H:%M:%S").time()
    flight['stats']['starttime_seconds'] = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second
    flight['stats']['sektoren_count'] = len(flight['stats']['sektoren'])
    # flight['stats']['prettystarttime'] = f"{flight['stats']['starttime_seconds'] // 3600:02}:{(flight['stats']['starttime_seconds'] % 3600) // 60:02}"
    flight['stats']['prettyflighttime'] = pretty_duration(flight['stats']['duration'])
    flight['stats']['xcscore'] = round(flight['BestTaskPoints'])
    flight['stats']['maxspeed'] = round(flight['MaxSpeed']*3.6)  # m/s to km/h
    flight['stats']['avgspeed'] = round(flight['BestTaskSpeed']*3.6)  # m/s to km/h
    flight['stats']['maxclimb'] = round(flight['MaxClimb'], 1)
    flight['stats']['minclimb'] = round(flight['MinClimb'], 1)

stat_keys = [
    #'starttime_seconds', 
    'duration', 'drehueberschuss', 'sektoren_count', 'maxalt', 'xcscore', 'maxspeed', 'avgspeed', 'maxclimb', 'minclimb']
# calculate median flight stats
# (by storing each category in a sorted list, also used for later distribution analysis)
sorted_stats = {}
for k in stat_keys:
    sorted_stats[k] = sorted([ f['stats'][k] for f in flight_data ])

median_stats = { k: vs[len(vs) // 2] for k, vs in sorted_stats.items() }
# median_stats['prettystarttime'] = f"{median_stats['starttime_seconds'] // 3600:02}:{(median_stats['starttime_seconds'] % 3600) // 60:02}"
median_stats['prettyflighttime'] = pretty_duration(median_stats['duration'])

# compute first and last rank of element in sorted list
def ranks(x, vs):
    first = vs.index(x) + 1
    last = len(vs) - vs[::-1].index(x)
    return (first, last)

# Now rank each flight
for flight in flight_data:
    scores = []
    for k in stat_keys:
        vs = sorted_stats[k]
        v = flight['stats'][k]
        (r1, r2) = ranks(v, vs)
        mid = len(vs)/2
        if r1 <= mid and r2 >= mid:
            scores.append(0)
        else:
            scores.append(min(abs(mid - r1), abs(mid - r2))/mid * 100)
    score = math.sqrt(sum([s*s for s in scores])/len(scores))
    flight['stats']['score'] = round(score, 1)

def finalize_stats(stats, covered):
    stats['sektoren'] = len(covered)
    if stats['left_turns'] > stats['right_turns']:
        stats['drehrichtung'] = "(nach links)"
        stats['drehueberschuss'] = stats['left_turns'] - stats['right_turns']
    elif stats['left_turns'] < stats['right_turns']:
        stats['drehrichtung'] = "(nach rechts)"
        stats['drehueberschuss'] = stats['right_turns'] - stats['left_turns']
    stats['prettyflighttime'] = pretty_duration(stats['flighttime'])

# Create per pilot website, and gather stats
pilots = []
pilottemplate = env.get_template("pilot.html")
sektor_pilots = {}
sektor_flights = {}
all_flights = []
for pid, pflights in flights.items():
    name = full_name(pflights[0])
    covered = set()

    # stats
    stats = {
        'schauiflights': 0,
        'lindenflights': 0,
        'flighttime': 0,
        'hikes': 0,
        'fotos': 0,
        'sektoren': 0,
        #'landepunkt1': 0,
        #'landepunkt2': 0,
        #'landepunkt3': 0,
        'drehrichtung': "",
        'drehueberschuss': 0,
        'left_turns': 0,
        'right_turns': 0,
        'sonderwertung': 0,
    }

    # if pid == '10564':
    #     stats['sonderwertung'] += 1
    # if pid == '14869':
    #     stats['sonderwertung'] += 3
    # if pid == '12218':
    #     stats['sonderwertung'] += 2
    # if pid == '771':
    #     stats['sonderwertung'] += 1
    if pid == '14475':
      stats['sonderwertung'] += 1  
    if pid == '14679':
      stats['sonderwertung'] += 1  

    # Best average flight
    best_avg_flight = min(pflights, key=lambda f: f['stats']['score'])
    best_avg_flight['is_best'] = True

    data = {}
    # data['lpradius1'] = constants.lpradius1
    # data['lpradius2'] = constants.lpradius2
    # data['lpradius3'] = constants.lpradius3
    data['flights'] = []
    for n, f in enumerate(pflights):
        id = f['IDFlight']

        sektoren = f['stats']['sektoren']
        for s in sektoren:
            if s not in sektor_flights:
                sektor_flights[s] = 0
            sektor_flights[s] += 1

        # Neue sektoren
        new = set(sektoren).difference(covered)
        covered.update(new)

        # update stats
        stats['flighttime'] += int(f['FlightDuration'])
        stats['left_turns'] += f['stats']['left_turns']
        stats['right_turns'] += f['stats']['right_turns']
        # if f['stats']['landepunktabstand'] < constants.lpradius1:
        #     stats['landepunkt1'] += 1
        # elif f['stats']['landepunktabstand'] < constants.lpradius2:
        #     stats['landepunkt2'] += 1
        # elif f['stats']['landepunktabstand'] < constants.lpradius3:
        #     stats['landepunkt3'] += 1

        if f['TakeoffWaypointName'] == "Schauinsland":
            stats['schauiflights'] += 1
        if f['TakeoffWaypointName'] == "Lindenberg":
            stats['lindenflights'] += 1

        is_hike = False
        if f['TakeoffWaypointName'] == "Schauinsland" and int(f['CountComments']) > 0:
            comments = json.load(open(f'_flights/{id}.comments.json'))
            for c in comments['data']:
                if str(c['FKAuthor']) == pid and bool(hike_and_fly_re.search(c["CommentText"])):
                    is_hike = True

        if is_hike:
            stats['hikes'] += 1

        has_fotos = int(f['HasPhotos']) > 0
        if has_fotos:
            stats['fotos'] += 1

        fd = {
          'pid': pid,
          'name': name,
          'n': n+1,
          'id': id,
          'datum': datetime.date.fromisoformat(f['FlightDate']).strftime("%d.%m."),
          'landeplatz': f['TakeoffWaypointName'],
          'flugzeit_sekunden': f['FlightDuration'],
          #'landepunktabstand_meter': f['stats']['landepunktabstand'],
          #'landepunktabstand': pretty_landepunktabstand(f['stats']['landepunktabstand']),
          'neue_sektoren': " ".join(sorted(list(new))),
          'neue_sektoren_anzahl': len(new),
          'fotos': has_fotos,
          'hike': is_hike,
          'stats': f['stats'],
          'is_best': 'is_best' in f,
          'url': f"https://de.dhv-xc.de/flight/{id}",
        }
        data['flights'].append(fd)
        all_flights.append(fd)

    # Finalize stats
    finalize_stats(stats, covered)

    # Sektor heat map
    for s in covered:
        if s not in sektor_pilots:
            sektor_pilots[s] = 0
        sektor_pilots[s] += 1

    pilots.append({
        'pid': pid,
        'name': name,
        'stats': stats,
        'best_flight': best_avg_flight,
    })

    # Write per-pilot website
    data['pid'] = pid
    data['name'] = name
    data['stats'] = stats
    data['now'] = now
    data['latest_flight'] = latest_flight
    data['count_flight'] = len(flight_data)
    data['best_flight'] = best_avg_flight
    pilottemplate\
      .stream(data) \
      .dump(open(f'_out/pilot{pid}.html', 'w'))


# Sort pilots (TODO)
pilots.sort(key = lambda p: p['best_flight']['stats']['score'])
for i, p in enumerate(pilots):
    p['rank'] = i + 1

# Turn statistics
turn_stats = {
  'least_rel_diff': min(
    [ (p['name'], p['pid'],
      100 * abs(p['stats']['left_turns'] - p['stats']['right_turns']) / \
      (p['stats']['left_turns'] + p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_rel_diff_left': max(
    [ (p['name'], p['pid'],
      100 * (p['stats']['left_turns'] - p['stats']['right_turns']) / \
      (p['stats']['left_turns'] + p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_abs_diff_left': max(
    [ (p['name'], p['pid'], (p['stats']['left_turns'] - p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_rel_diff_right': max(
    [ (p['name'], p['pid'],
      100 * (p['stats']['right_turns'] - p['stats']['left_turns']) / \
      (p['stats']['left_turns'] + p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_abs_diff_right': max(
    [ (p['name'], p['pid'], (p['stats']['right_turns'] - p['stats']['left_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
}

# Write main website
data = {}
data['pilots'] = pilots
data['now'] = now
data['latest_flight'] = latest_flight
data['count_flight'] = len(flight_data)
data['turn_stats'] = turn_stats
data['median_stats'] = median_stats
env.get_template("index.html") \
  .stream(data) \
  .dump(open(f'_out/index.html', 'w'))

# Write main data as CSV
with open('_out/data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

# Write Flight data to CSV file

with open('flights.csv', 'w', newline='') as csvfile:
    w = csv.DictWriter(csvfile, all_flights[0].keys())
    w.writeheader()
    for fd in all_flights:
        w.writerow(fd)
