#!/usr/bin/env bash

set -e

limit=2000
year=2026

echo "flights.json: fetching"
for s in 0 500 1000 1500 2000
do
wget \
    --no-verbose \
	--load-cookies _tmp/cookies.txt \
	--save-cookies _tmp/cookies.txt \
        --keep-session-cookies \
    "https://de.dhv-xc.de/api/fli/flights?d0=1.1.$year&d1=15.9.$year&fkto%5B%5D=9306&fkto%5B%5D=11362&clubde%5B%5D=130&navpars=%7B%22start%22%3A$s%2C%22limit%22%3A$limit%7D" \
	-O _tmp/flights-$s.json.tmp
done

jq -s 'map (.data) | flatten' _tmp/flights-{0,500,1000,1500,2000}.json.tmp > _tmp/flights.json.tmp

echo -n "Flights before opt-out: "
jq 'length' < _tmp/flights.json.tmp
# pilot opt-out
# jq 'map(select(.FKPilot != "1284" or (.IDFlight|tonumber) <= 1908028))' < _tmp/flights.json.tmp > _tmp/flights.json
# jq 'map(select(.FKPilot != 1284))' < _tmp/flights.json.tmp > _tmp/flights.json
cat < _tmp/flights.json.tmp > _tmp/flights.json
echo -n "Flights after opt-out: "
jq 'length' < _tmp/flights.json
