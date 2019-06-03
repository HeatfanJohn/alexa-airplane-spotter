from bs4 import BeautifulSoup
from pymongo import MongoClient
import json
import requests
import re
import csv
import datetime
from logger import logger
import settings

route_data_endpoint = 'https://www.flightradar24.com/data/aircraft/{}'

with open('icao_codes.tsv', 'r') as f:
    airplane_codes = {}
    icao_codes = csv.reader(f, delimiter='\t')
    next(icao_codes, None)
    for row in icao_codes:
        code, iata, name = row
        airplane_codes[code] = name


def get_departure_airport(row):
    airport = row.findAll('td')[3].text
    airport_code = re.search('[A-Z]{3}', airport).group(0)
    return airport_code


def get_tz_offset(airport_code):
    client = MongoClient('localhost:27017')
    db = client.AircraftData
    result = db.AirportTZ.find_one({
        'code': airport_code
    })
    return abs(result['offset']['dst'])


def departure_time_for_row(tr):
    tds = tr.findAll('td')
    logger.info(len(tds))
    logger.info(tds[7].text.strip())
    if len(tds) < 7 or (tds[7].text.strip() in ['-', u'\u2014']):
        return None
    year_month_day = tds[2].text.strip()
    logger.info(year_month_day)
    time_depart = tds[7].text.strip()
    logger.info(time_depart)
    localtime = datetime.datetime.strptime('{} {}'.format(year_month_day, time_depart), '%d %b %Y %H:%M')
    departure_airport = get_departure_airport(tr)
    return localtime - datetime.timedelta(hours=get_tz_offset(departure_airport))


def std_in_past(row):
    std = departure_time_for_row(row)
    logger.info(std)
    logger.info(datetime.datetime.now())
    return std is None or std < datetime.datetime.now()


def most_recent_departure(soup):
    trs = soup.findAll('tr')[1:] # first tr in html isn't a flight row
    return next((tr for tr in trs if std_in_past(tr) and tr is not None), None)


def scrape_route_data(reg_no):
    url = route_data_endpoint.format(reg_no) #flightradar24.com/data/aircraft/{}
    logger.info("url={}".format(url))
    
    # Get a copy of the default headers that requests would use
    headers = requests.utils.default_headers()

    headers.update(
        {
#           'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.94 Safari/537 .36'
            'User-Agent': 'curl/7.38.0'
        }
    )

    res = requests.get(url, headers=headers)
    route_row = most_recent_departure(BeautifulSoup(res.text, "lxml"))
    if route_row is None:
        return None, None

    depart = route_row.findAll('td')[3].text
    depart = re.sub('\([A-Z]{3}\)', '', depart).strip()
    arrive = route_row.findAll('td')[4].text
    arrive = re.sub('\([A-Z]{3}\)', '', arrive).strip()

    return depart, arrive


def db_results(icao24):
    client = MongoClient('localhost:27017')
    db = client.AircraftData
    result = db.Registration.find_one({
        'icao': icao24.upper()
    })

    if not result:
        return None

    airline = result['operator'].encode('ascii')
    reg_no = result['regid'].encode('ascii')
    aircraft = result['type'].encode('ascii')

    return reg_no, aircraft, airline


def flight_info(flight):
    results = db_results(flight.icao24)

    if not results:
        logger.info('could find flight in db (flight={})'.format(flight))
        data = {
                'aircraft': None,
                'airline': 'Unknown ICAO',
                'altitude': flight.altitude,
                'velocity': flight.velocity,
                'airport_depart': None,
                'airport_arrive': None
        }
        return data

    reg_no, aircraft, airline = results
    aircraft = ''.join(aircraft.split('-')[:-1])

    data = {
            'aircraft': aircraft,
            'airline': airline,
            'altitude': flight.altitude,
            'velocity': flight.velocity
    }

    if not reg_no:
        logger.info('couldn\'t find aircraft icao ({}) in db'.format(flight.icao24))
        return data

    route_results = scrape_route_data(reg_no)

    if route_results:
        from_airport, to_airport = route_results
        data.update({
                     'airport_depart': from_airport,
                     'airport_arrive': to_airport
                    })
    return data
