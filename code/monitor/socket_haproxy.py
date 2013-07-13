#!/usr/bin/env python

# Copyright (C) 2013 Michele Mazzucco
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


__author__    = 'Michele Mazzucco <Michele.Mazzucco@ut.ee>'
'''
Monitors the status of HAProxy. Most of this code is based on HATop, see
http://feurix.org/projects/hatop/
'''

# requires file .boto/boto.cfg, see http://code.google.com/p/boto/wiki/BotoConfig

import re
import socket
from socket import error as SocketError
import time, sys, logging

import stats


# ------------------------------------------------------------------------- #
#                               GLOBALS                                     #
# ------------------------------------------------------------------------- #

# UNIX socket used by haproxy
SOCKET_PATH = '/tmp/haproxy'

# Max number of requests running or waiting: add reserves if exceeded
HAPROXY_MAX_QUEUE = 100
# Min number of requests running or waiting: remove reserves if lower
HAPROXY_MIN_QUEUE = 100

RESERVES_ON = False


# Settings of interactive command session over the unix-socket
HAPROXY_CLI_BUFSIZE = 4096
HAPROXY_CLI_TIMEOUT = 100000
HAPROXY_CLI_PROMPT = '> '
HAPROXY_CLI_CMD_SEP = ';'
HAPROXY_CLI_CMD_TIMEOUT = 1
HAPROXY_CLI_MAXLINES = 1000

# Settings of the embedded CLI
CLI_MAXLINES = 1000
CLI_MAXHIST = 100
CLI_INPUT_LIMIT = 200
CLI_INPUT_RE = re.compile('[a-zA-Z0-9_:\.\-\+; /#%]')
CLI_INPUT_DENY_CMD = ['prompt', 'set timeout cli', 'quit']


HAPROXY_INFO_RE = {
'software_name':    re.compile('^Name:\s*(?P<value>\S+)'),
'software_version': re.compile('^Version:\s*(?P<value>\S+)'),
'software_release': re.compile('^Release_date:\s*(?P<value>\S+)'),
'nproc':            re.compile('^Nbproc:\s*(?P<value>\d+)'),
'procn':            re.compile('^Process_num:\s*(?P<value>\d+)'),
'pid':              re.compile('^Pid:\s*(?P<value>\d+)'),
'uptime':           re.compile('^Uptime:\s*(?P<value>[\S ]+)$'),
'maxconn':          re.compile('^Maxconn:\s*(?P<value>\d+)'),
'curconn':          re.compile('^CurrConns:\s*(?P<value>\d+)'),
'maxpipes':         re.compile('^Maxpipes:\s*(?P<value>\d+)'),
'curpipes':         re.compile('^PipesUsed:\s*(?P<value>\d+)'),
'tasks':            re.compile('^Tasks:\s*(?P<value>\d+)'),
'runqueue':         re.compile('^Run_queue:\s*(?P<value>\d+)'),
'node':             re.compile('^node:\s*(?P<value>\S+)'),
}

HAPROXY_STAT_MAX_SERVICES = 100
HAPROXY_STAT_COMMENT = '#'
HAPROXY_STAT_SEP = ','
HAPROXY_STAT_FILTER_RE = re.compile(
        '^(?P<iid>-?\d+)\s+(?P<type>-?\d+)\s+(?P<sid>-?\d+)$')
HAPROXY_STAT_PROXY_FILTER_RE = re.compile(
        '^(?P<pxname>[a-zA-Z0-9_:\.\-]+)$')
HAPROXY_STAT_CSV = [
# Note: Fields must be listed in correct order, as described in:
# http://haproxy.1wt.eu/download/1.4/doc/configuration.txt [9.1]

# TYPE  FIELD

(str,   'pxname'),          # proxy name
(str,   'svname'),          # service name (FRONTEND / BACKEND / name)
(int,   'qcur'),            # current queued requests
(int,   'qmax'),            # max queued requests
(int,   'scur'),            # current sessions
(int,   'smax'),            # max sessions
(int,   'slim'),            # sessions limit
(int,   'stot'),            # total sessions
(int,   'bin'),             # bytes in
(int,   'bout'),            # bytes out
(int,   'dreq'),            # denied requests
(int,   'dresp'),           # denied responses
(int,   'ereq'),            # request errors
(int,   'econ'),            # connection errors
(int,   'eresp'),           # response errors (among which srv_abrt)
(int,   'wretr'),           # retries (warning)
(int,   'wredis'),          # redispatches (warning)
(str,   'status'),          # status (UP/DOWN/NOLB/MAINT/MAINT(via)...)
(int,   'weight'),          # server weight (server), total weight (backend)
(int,   'act'),             # server is active (server),
                            # number of active servers (backend)
(int,   'bck'),             # server is backup (server),
                            # number of backup servers (backend)
(int,   'chkfail'),         # number of failed checks
(int,   'chkdown'),         # number of UP->DOWN transitions
(int,   'lastchg'),         # last status change (in seconds)
(int,   'downtime'),        # total downtime (in seconds)
(int,   'qlimit'),          # queue limit
(int,   'pid'),             # process id
(int,   'iid'),             # unique proxy id
(int,   'sid'),             # service id (unique inside a proxy)
(int,   'throttle'),        # warm up status
(int,   'lbtot'),           # total number of times a server was selected
(str,   'tracked'),         # id of proxy/server if tracking is enabled
(int,   'type'),            # (0=frontend, 1=backend, 2=server, 3=socket)
(int,   'rate'),            # number of sessions per second
                            # over the last elapsed second
(int,   'rate_lim'),        # limit on new sessions per second
(int,   'rate_max'),        # max number of new sessions per second
(str,   'check_status'),    # status of last health check
(int,   'check_code'),      # layer5-7 code, if available
(int,   'check_duration'),  # time in ms took to finish last health check
(int,   'hrsp_1xx'),        # http responses with 1xx code
(int,   'hrsp_2xx'),        # http responses with 2xx code
(int,   'hrsp_3xx'),        # http responses with 3xx code
(int,   'hrsp_4xx'),        # http responses with 4xx code
(int,   'hrsp_5xx'),        # http responses with 5xx code
(int,   'hrsp_other'),      # http responses with other codes (protocol error)
(str,   'hanafail'),        # failed health checks details
(int,   'req_rate'),        # HTTP requests per second
(int,   'req_rate_max'),    # max number of HTTP requests per second
(int,   'req_tot'),         # total number of HTTP requests received
(int,   'cli_abrt'),        # number of data transfers aborted by client
(int,   'srv_abrt'),        # number of data transfers aborted by server
]
HAPROXY_STAT_NUMFIELDS = len(HAPROXY_STAT_CSV)
HAPROXY_STAT_CSV = [(k, v) for k, v in enumerate(HAPROXY_STAT_CSV)]

class sock:
    
    def __init__(self, path=SOCKET_PATH):
        self.path = path
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.settimeout(1)
        #self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        #self._socket.setblocking(0)
        #self._socket.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 0)
        
    def _recv(self):
        # socket.recv() wrapper raising SocketError if we receive
        # EOF before seeing the interactive socket prompt.
        data = self._socket.recv(HAPROXY_CLI_BUFSIZE)
        if not data:
            raise SocketError('error while waiting for prompt')
        return data

    def connect(self):
        # Initialize socket connection
        self._socket.connect(self.path)
        self._socket.settimeout(HAPROXY_CLI_CMD_TIMEOUT)

        # Enter the interactive socket mode. This requires HAProxy 1.4+ and
        # allows us to error out early if connected to an older version.
        try:
            self.send('prompt')
            self.wait()
            self.send('set timeout cli %d' % HAPROXY_CLI_TIMEOUT)
            self.wait()
        except SocketError:
            raise SocketError('error while initializing interactive mode')

    def close(self):
        try:
            self.send('quit')
        except:
            pass
        
        # adding shutdown (michele)
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        
        try:
            self._socket.close()
        except:
            pass

    def send(self, cmdline):
        '''
        Returns the number of bytes sent
        '''
        return self._socket.send('%s\n' % cmdline)

    def wait(self):
        # Wait for the prompt and discard data.
        rbuf = ''
        while not rbuf.endswith(HAPROXY_CLI_PROMPT):
            data = self._recv()
            rbuf = rbuf[-(len(HAPROXY_CLI_PROMPT)-1):] + data

    def recv(self):
        # Receive lines until HAPROXY_CLI_MAXLINES or the prompt is reached.
        # If the prompt was still not found, discard data and wait for it.
        linecount = 0
        rbuf = ''
        while not rbuf.endswith(HAPROXY_CLI_PROMPT):

            if linecount == HAPROXY_CLI_MAXLINES:
                data = self._recv()
                rbuf = rbuf[-(len(HAPROXY_CLI_PROMPT)-1):] + data
                continue

            data = self._recv()
            rbuf += data

            while linecount < HAPROXY_CLI_MAXLINES and '\n' in rbuf:
                line, rbuf = rbuf.split('\n', 1)
                linecount += 1
                yield line

class SocketData:

    def __init__(self, socket, socket_path=SOCKET_PATH):
        self.socket = socket
        self.pxcount = 0
        self.svcount = 0
        self.info = {}
        self.stat = {}
        self._filters = set()
        self.socket_path = socket_path

    def register_stat_filter(self, stat_filter):

        # Validate and register filters
        stat_filter_set = set(stat_filter)
        for filter in stat_filter_set:
            match = HAPROXY_STAT_FILTER_RE.match(filter)
            if not match:
                raise ValueError('invalid stat filter: %s' % filter)
            self._filters.add((
                    int(match.group('iid'), 10),
                    int(match.group('type'), 10),
                    int(match.group('sid'), 10),
            ))

    def register_proxy_filter(self, proxy_filter):

        # Validate filters
        proxy_filter_set = set(proxy_filter)
        for filter in proxy_filter_set:
            if not HAPROXY_STAT_PROXY_FILTER_RE.match(filter):
                raise ValueError('invalid proxy filter: %s' % filter)

        # Convert proxy filters into more efficient stat filters
        self.socket.send('show stat')
        pxstat, pxcount, svcount = parse_stat(self.socket.recv())

        proxy_iid_map = {} # {pxname: iid, ...}

        for pxname in proxy_filter_set:
            for iid in pxstat:
                for sid in pxstat[iid]:
                    if pxstat[iid][sid]['pxname'] == pxname:
                        proxy_iid_map[pxname] = iid
                    break
                if pxname in proxy_iid_map:
                    break

        for pxname in proxy_filter_set:
            if not pxname in proxy_iid_map:
                raise RuntimeError('proxy not found: %s' % pxname)

        # Register filters
        for iid in proxy_iid_map.itervalues():
            self._filters.add((iid, -1, -1))

    def update_info(self):
        self.socket.send('show info')
        iterable = self.socket.recv()
        self.info = parse_info(iterable)
        
        
    def reconnect(self):
        '''
        Reconnects the socket
        '''
        try:
            self.socket.close()
        except Exception:
            pass # ignore
        
        self.socket = None
        self.socket = sock(self.socket_path)
        self.socket.connect()
        self.update_stat()
        

    def update_stat(self):
        # Store current data
        pxcount_old = self.pxcount
        svcount_old = self.svcount
        stat_old = self.stat

        # Reset current data
        self.pxcount = 0
        self.svcount = 0
        self.stat = {}

        if self._filters:
            for filter in self._filters:
                self.socket.send('show stat %d %d %d' % filter)
                filter_stat, filter_pxcount, filter_svcount = \
                        parse_stat(self.socket.recv())

                if filter_pxcount == 0:
                    #raise RuntimeError('stale stat filter: %d %d %d' % filter)
                    logging.debug('No stats data available, reconnecting')
                    self.reconnect()
                    

                self.pxcount += filter_pxcount
                self.svcount += filter_svcount
                self.stat.update(filter_stat)
        else:
            print 'showing stat'
            self.socket.send('show stat')
            self.stat, self.pxcount, self.svcount = \
                    parse_stat(self.socket.recv())

        # deal with HAProxy reconfiguration reload
        if self.pxcount == 0:
            logging.info('No stats data available, reconnecting')
            self.reconnect()
            #raise RuntimeWarning('no stat data available')

        # Warn if the HAProxy configuration has changed on-the-fly
        pxdiff = 0
        svdiff = 0

        if self.pxcount < pxcount_old:
            pxdiff -= pxcount_old - self.pxcount
        if pxcount_old > 0 and self.pxcount > pxcount_old:
            pxdiff += self.pxcount - pxcount_old
        if self.svcount < svcount_old:
            svdiff -= svcount_old - self.svcount
        if svcount_old > 0 and self.svcount > svcount_old:
            svdiff += self.svcount - svcount_old

        if pxdiff != 0 or svdiff != 0:
        #    raise RuntimeWarning(
            logging.warn(
                    'config changed: proxy %+d, service %+d '
                    '(reloading...)' % (pxdiff, svdiff))


# ------------------------------------------------------------------------- #
#                                HELPERS                                    #
# ------------------------------------------------------------------------- #

def get_idx(field):
    return filter(lambda x: x[1][1] == field, HAPROXY_STAT_CSV)[0][0]


def parse_stat(iterable):
    pxcount = svcount = 0
    pxstat = {} # {iid: {sid: svstat, ...}, ...}

    idx_iid = get_idx('iid')
    idx_sid = get_idx('sid')

    for line in iterable:
        if not line:
            continue
        if line.startswith(HAPROXY_STAT_COMMENT):
            continue # comment
        if line.count(HAPROXY_STAT_SEP) < HAPROXY_STAT_NUMFIELDS:
            continue # unknown format

        csv = line.split(HAPROXY_STAT_SEP, HAPROXY_STAT_NUMFIELDS)

        # Skip further parsing?
        if svcount > HAPROXY_STAT_MAX_SERVICES:
            try:
                iid = csv[idx_iid]
                iid = int(iid, 10)
            except ValueError:
                raise RuntimeError(
                        'garbage proxy identifier: iid="%s" (need %s)' %
                        (iid, int))
            try:
                sid = csv[idx_sid]
                sid = int(sid, 10)
            except ValueError:
                raise RuntimeError(
                        'garbage service identifier: sid="%s" (need %s)' %
                        (sid, int))
            if iid not in pxstat:
                pxcount += 1
                svcount += 1
            elif sid not in pxstat[iid]:
                svcount += 1
            continue

        # Parse stat...
        svstat = {} # {field: value, ...}

        for idx, field in HAPROXY_STAT_CSV:
            field_type, field_name = field
            value = csv[idx]

            try:
                if field_type is int:
                    if len(value):
                        value = int(value, 10)
                    else:
                        value = 0
                elif field_type is not type(value):
                        value = field_type(value)
            except ValueError:
                raise RuntimeError('garbage field: %s="%s" (need %s)' % (
                        field_name, value, field_type))

            # Special case
            if field_name == 'status' and value == 'no check':
                value = '-'
            elif field_name == 'check_status' and svstat['status'] == '-':
                value = 'none'

            svstat[field_name] = value

        # Record result...
        iid = svstat['iid']
        stype = svstat['type']

        if stype == 0 or stype == 1:  # FRONTEND / BACKEND
            id = svstat['svname']
        else:
            id = svstat['sid']

        try:
            pxstat[iid][id] = svstat
        except KeyError:
            pxstat[iid] = { id: svstat }
            pxcount += 1
        svcount += 1

    return pxstat, pxcount, svcount


def parse_info(iterable):
    info = {}
    for line in iterable:
        line = line.strip()
        if not line:
            continue
        for key, regexp in HAPROXY_INFO_RE.iteritems():
            match = regexp.match(line)
            if match:
                info[key] = match.group('value')
                break

    for key in HAPROXY_INFO_RE.iterkeys():
        if not key in info:
            raise RuntimeError('missing "%s" in info data' % key)

    return info




def monitor_haproxy(sleep_sec=1, socket_path=SOCKET_PATH):
    '''
    Monitors the status of HAProxy
    
    :type sleep_sec: int No. of seconds between two consecutive status snapshots
    :type socket_path: string Path to the UNIX socket
    '''
    s = sock(socket_path)
    
    haproxy_stats = stats.HAProxy()
    arr_rate = stats.ArrivalRate()
    
    try:
        try:
            data = SocketData(s, socket_path) # socket_path is used to reconnect
            # the 2nd 1 means FRONTEND, see documentation (sec. 9.2)
            filter_frontend = ['-1 1 -1'] 
            data.register_stat_filter(filter_frontend)
            s.connect()
            logging.info('Socket connected')
            #s.send("show info")
            #iterable = s.recv()
            #info = parse_info(iterable)
            
            go = True
            while go:
                # Convert proxy filters into more efficient stat filters
                #s.send('show stat -1 2 -1') # see sec. 9.2 http://haproxy.1wt.eu/download/1.4/doc/configuration.txt
                #pxstat, pxcount, svcount = parse_stat(s.recv())
                #print pxstat
                #["BACKEND"]
                #print pxcount
                #print svcount
                
                data.update_stat()
                stat = data.stat; # dictionary
                #print stat
                # current number of jobs inside the system (waiting or being executed)
                frontend = stat[1]["FRONTEND"] # dictionary
                
                cur_time = time.time()
                haproxy_stats.update(frontend, cur_time)
                arr_rate.update(frontend['stot'], cur_time)
                
                #qcur = frontend['qcur'] # 1 is the key, see filter
                scur = frontend['scur'] # 1 is the key, see filter
                #req_rate = frontend['req_rate']
                #req_rate_max = frontend['req_rate_max']
                #req_tot = frontend['req_tot']
                
                #logging.info("queue %d, jobs in system %d, req. rate %d, req. rate. max %d, total req. %d" % 
                #             (qcur, scur, req_rate, req_rate_max, req_tot))
                if scur > HAPROXY_MAX_QUEUE and RESERVES_ON == False:
                    logging.warn("Jobs in system %d" % scur)
                #    reserves.add_reserves()
                elif scur < HAPROXY_MIN_QUEUE and RESERVES_ON == True:
                    logging.warn("Jobs in system %d" % scur)
                    #reserves.remove_reserves()
                
                # 1 sec. circa, see http://mail.python.org/pipermail/tutor/2006-November/050915.html
                try:
                    time.sleep(sleep_sec)
                except KeyboardInterrupt: # CTRL+D
                    go = False
                    logging.info('Keyboard interrupt')
        except SocketError, e:
            logging.error('socket error: %s' % e)
            sys.exit(2)
    
    finally:
        s.close()
        haproxy_stats.close()
        
    logging.info("Exiting...") 
    
    
def do_exit(signum, stack):
    sys.exit(0)

def receive_alarm(signum, stack):
    print 'Alarm :', signum, time.ctime()

# main
if __name__ == '__main__':
    # http://docs.python.org/howto/logging.html
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.INFO)

    #signal.signal(signal.SIGINT, do_exit)
    monitor_haproxy(2)
    