#!/usr/bin/env python
#
# Data-gathering tool that simultaneously grabs data from the thermostat
# and weather undergroun.
import sys
try:
    import rrdtool
except ImportError:
    print >> sys.stderr, "Requires python-rrdtool to be installed"
    sys.exit(-1)

try:
    import simplejson as json
except ImportError:
    print >> sys.stderr, "Requires python-simplejson to be installed"
    sys.exit(-1)

try:
    import yaml
except ImportError:
    print >> sys.stderr, "Requires python-yaml to be installed"
    sys.exit(-1)

import urllib2
import StringIO
import os
import time
import logging
from xml.etree import ElementTree as ET

SECONDS_PER_DAY = 86400
SECONDS_PER_YEAR = 365 * SECONDS_PER_DAY

class Database:

    FIELDS = [('interior_temp', 'GAUGE', 300, 'U', 'U'),
              ('target_heat', 'GAUGE', 300, 'U', 'U'),
              ('target_cool', 'GAUGE', 300, 'U', 'U'),
              ('fan_state', 'GAUGE', 300, '0', '1'),
              ('exterior_temp', 'GAUGE', 300, 'U', 'U'),
              ('solar_radiation', 'GAUGE', 300, 'U', 'U'),
              ('wind_speed', 'GAUGE', 300, 'U', 'U'),
              ('wind_gust', 'GAUGE', 300, 'U', 'U'),
              ('wind_deg', 'GAUGE', 300, 'U', 'U')]

    def __init__(self, sample_period, dbfile="monitor.rrd"):
        self.dbfile = dbfile
        if not os.path.exists(self.dbfile):
            rrdargs = []
            rrdargs.extend(["DS:%s:%s:%s:%s:%s" % x for x in Database.FIELDS])
            rrdargs.append('RRA:AVERAGE:0.5:1:%s' % (SECONDS_PER_YEAR / sample_period))
            rrdargs.append('RRA:LAST:0.5:1:%s' % (SECONDS_PER_YEAR / sample_period))
            rrdargs.append('RRA:MIN:0.5:1:%s' % (SECONDS_PER_YEAR / sample_period))
            rrdargs.append('RRA:MAX:0.5:1:%s' % (SECONDS_PER_YEAR / sample_period))

            rrdtool.create('monitor.rrd',
                           '--start', 'now-5m',
                           '--step', str(CONFIGURATION['period']),
                           *rrdargs)

    def append(self, data):
        now = time.time()
        step = int(now / CONFIGURATION['period']) * CONFIGURATION['period']
        logging.debug("Updating data @ %s; nearest step %s", now, step)

        update_str = [str(step)]
        for name, type_, period, min_, max_ in Database.FIELDS:
            try:
                d = data[name]
                if d == None:
                    d = 'U'
                else:
                    d = str(d)
            except KeyError, e:
                d = 'U'
            update_str.append(d)

        update_str = ":".join(update_str)

        logging.debug("Adding %s to rrd", update_str)
        rrdtool.update(self.dbfile, update_str) 

if __name__ == "__main__":
    # Load configuration
    if not os.path.exists("monitor.yaml"):
        print >> sys.stderr, "Could not fine monitor.yaml"
        sys.exit(-1)

    CONFIGURATION = yaml.load(open("monitor.yaml"))

    logging.basicConfig(level=logging.DEBUG)

    db = Database(CONFIGURATION['period'])

    while True:
        data = {}
       
        try:
            d = urllib2.urlopen(CONFIGURATION['weather_underground_url'] % (CONFIGURATION['weather_underground_station']))
            wu = ET.parse(d).getroot()
            data['exterior_temp'] = wu.findtext('temp_f')
            data['solar_radiation'] = wu.findtext('solar_radiation')
            data['wind_speed'] = wu.findtext('wind_mph')
            data['wind_gust'] = wu.findtext('wind_gust_mph')
            data['wind_deg'] = wu.findtext('wind_degrees')
        except Exception, e:
            logging.exception("Error retreiving data from Weather Underground")

        try:	    
            d = urllib2.urlopen(CONFIGURATION['thermostat_url']+"/tstat")
            tstat = json.load(d)
            data['interior_temp'] = tstat['temp']
            data['fan_state'] = tstat['fstate']
            if tstat.has_key('t_heat'):
                data['target_heat'] = tstat['t_heat']
            else:
                data['target_heat'] = -1.0
            if tstat.has_key('t_cool'):
                data['target_cool'] = tstat['t_cool']
            else:
                data['target_cool'] = -1.0
        except Exception, e:
            logging.exception("Error retreiving data from Thermostat")

        try:
            db.append(data)
        except Exception, e:
            logging.exception("Error updating database")

        time.sleep(CONFIGURATION['period'])
