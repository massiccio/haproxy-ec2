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


'''
Created on Feb 15, 2012

@author: michele
'''


import psutil
import os, logging, subprocess, string, shlex, time
# http://stackoverflow.com/questions/826082/python-finding-uid-gid-for-a-given-username-groupname-for-os-chown
import csv
from string import atol, atof

import haproxy_configuration
import commons as utils
from psutil.error import AccessDenied

NET = 'net.csv' # 1st value received bytes, 2nd value sent bytes
CPU = 'cpu.csv'
CONNECTIONS = 'conn.csv'
LOAD = 'load.csv' # 1, 5 and 15 minutes
MEMORY = 'memory.csv'
HAPROXY = 'haproxy.csv'
ARR_RATE = 'arr_rate.csv'
COST = 'cost.csv'



HAPROXY_STAT_LOG = [
#FIELD
'qcur',            # current queued requests
'act',              # server is active (server), number of active servers (backend)
'scur',            # current sessions
'rate',            # HTTP requests per second (req_rate does now work)
'stot',            # total number of HTTP requests received (req_tot does not work)
'bin',             # bytes in
'bout',            # bytes out
'ereq',            # request errors
'econ',            # connection errors
'eresp',          # response errors (among which srv_abrt)
'hrsp_1xx',        # http responses with 1xx code
'hrsp_2xx',        # http responses with 2xx code
'hrsp_3xx',        # http responses with 3xx code
'hrsp_4xx',        # http responses with 4xx code
'hrsp_5xx',        # http responses with 5xx code
'hrsp_other',      # http responses with other codes (protocol error)
'cli_abrt',        # number of data transfers aborted by client
'srv_abrt'         # number of data transfers aborted by server
]



class Monitor():
    
    def __init__(self, path, buffering=2048):
        self.file_open = False
        self.f = open(path, 'w', buffering)
        utils.fix_file_permissions(self.f)
        self.file_open = True
        
        self.__tstamp = time.time()
        
        
    def get_creation_time(self):
        '''
        Gets the time when this object was created
        :rtype: float
        '''
        return self.__tstamp
        
    
    def close(self):
        '''
        Closes the file
        '''
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()
        self.file_open = False
        

    def is_file_open(self):
        '''
        Returns True if the file is open, False otherwise
        '''
        return self.file_open


class Memory(Monitor):
    '''
    Monitors memory usage
    '''
    def __init__(self, path=MEMORY, msg=None):
        Monitor.__init__(self, path)
        
        self.f.write('# Memory usage, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, used phy. mem. (MB),' 
        #    'free phy. mem. (%), used virt. mem. (MB), free virt. mem. (%),'
        #    '[cached memory and physical memory buffers in bytes (Linux '
        #    'only)]\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        
        row = []
        row.append('# event')
        row.append('time')
        row.append('used_phy_mem (MB)')
        row.append('used_phy_mem (%)')
        row.append('used_vm (MB)')
        row.append('used_vm (%)')
        row.append('cached_mem (MB')
        row.append('mem_buff (MB)')
        self.writer.writerow(row)
        
        
        self.counter = 0L
        if msg != None:
            self.f.write('# %s' % msg)
        
        if os.uname()[0] == 'Linux':
            self.linux = True
        else:
            self.linux = False


    def update(self, cur_time):
        self.counter += 1L
        row = []
        row.append(self.counter)
        row.append('%.2f' % (cur_time - self.get_creation_time()))
        pymem = psutil.phymem_usage()
        vmem = psutil.virtmem_usage()
        
        row.append('%.2f' % (atof(pymem[1]) / (1024.0 * 1024.0)))
        row.append('%.2f' % pymem[3])
        row.append('%.2f' % (atof(vmem[1]) / (1024.0 * 1024.0)))
        row.append('%.2f' % vmem[3])
        
        # cached memory and physical memory buffers on the system
        if self.linux == True:
            row.append('%d' % (psutil.cached_phymem() / (1024.0 * 1024.0)))
            row.append('%d' % (psutil.phymem_buffers() / (1024.0 * 1024.0)))
        
        self.writer.writerow(row)
    


class Connections(Monitor):
    '''
    Monitors the connections open by HAProxy. The process monitoring HAProxy
    should run with the same privileges (at least) of HAProxy, or it will fail.
    '''
    
    def __init__(self, path=CONNECTIONS, msg=None):
        '''
        Note: this method requires root access (sudo)
        '''
        utils.check_if_sudo()
        
        Monitor.__init__(self, path)
        
        self.f.write('# No. of connections, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, TCP conn, summ all conn. open by the HAProxy process\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        row = []
        row.append('# event')
        row.append('time')
        row.append('tcp_conn')
        row.append('all_conn')
        self.writer.writerow(row)
        
        self.counter = 0L
        if msg != None:
            self.f.write('# %s' % msg)
    
    
    
    def search_haproxy_proc(self):
        for p in psutil.process_iter():
            if p.name == 'haproxy':
                return p
        return None
    
    
    def __update_conn(self, haproxy_process, cur_time):
        if haproxy_process.name == 'haproxy':
            tcp = haproxy_process.get_connections(kind='tcp')
            all_conn = haproxy_process.get_connections(kind='all')
            #now = datetime.datetime.now()
            #print "Time {0}, conn. {1}".format(now, len(connections))
            
            #self.last = now # update last                    
            self.counter += 1L
            row = []
            row.append(self.counter)
            row.append('%.2f' % (cur_time - self.get_creation_time()))
            row.append('%d' % len(tcp))
            row.append('%d' % len(all_conn))
            self.writer.writerow(row)
        else:
            logging.error("Wrong process %s: unable to get stats!" % haproxy_process.name)
            
    
    def update(self, cur_time):
        pid_file = haproxy_configuration.PID_FILE
        if os.path.exists(pid_file):
            with open(pid_file, "r") as fp:
                pid = fp.readline()
                pid = int(pid.strip()) # trasform from string to int
                try:
                    if psutil.pid_exists(pid) == True:
                        haproxy_process = psutil.Process(pid)
                        self.__update_conn(haproxy_process, cur_time)
                    else:
                        logging.error('Pid %d does not exist' % pid)
                    
                except psutil.NoSuchProcess as (errno): # might terminate even if it was running before
                    logging.error("Is HAProxy running?: {0}".format(errno))
                except AccessDenied, e:
                    logging.fatal('Are you running as root/via sudo {0}?'.format(e.msg))
                    raise e
                except IOError as (errno, msg):
                    logging.error("Unable to open {0}: {1}, {2}".format(pid_file, errno, msg))
        
        else: # the file does not exist, maybe the process is not a daemon
            haproxy_process = self.search_haproxy_proc()
            if haproxy_process == None:
                logging.warn("{0} does not exist: is HAProxy running as a daemon?".format(pid_file))
            else:
                self.__update_conn(haproxy_process, cur_time)


class Cpu(Monitor):
    '''
    Monitors the CPU usage
    '''
    def __init__(self, path=CPU, msg=None):
        Monitor.__init__(self, path)
        
        self.f.write('# CPU usage, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, avg. cpu (%), list of cpu usage for each core/CPU\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        row = []
        row.append('# event')
        row.append('time')
        row.append('avg_cpu (%)')
        row.append('cpu_usage [per core]')
        self.writer.writerow(row)
        
        
        self.counter = 0L
        if msg != None:
            self.f.write('# %s' % msg)
        
        
    def update(self, cur_time):  
        self.counter += 1L
        row = []
        row.append(self.counter)
        row.append('%.2f' % (cur_time - self.get_creation_time()))
        # total
        row.append('%.2f' % psutil.cpu_percent(interval=0, percpu=False))
        # split by CPU/core
        for perc in psutil.cpu_percent(interval=0, percpu=True):
            row.append('%.2f' % perc)
        self.writer.writerow(row)
        

class Load(Monitor):
    '''
    Monitors the load, see 'uptime'
    '''
    
    def __init__(self, path=LOAD, msg = None):
        Monitor.__init__(self, path)
        
        self.last = self.get_creation_time() # records the last time this method was invoked
        self.f.write('# Load, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, load at 1 min, load at 5 mins, load at 15 mins\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        row = []
        row.append('# event')
        row.append('time')
        row.append('load_1')
        row.append('load_5')
        row.append('load_15')
        self.writer.writerow(row)
        
        
        self.counter = 0L
        if msg != None:
            self.f.write('# %s' % msg)
            
            
    def update(self, cur_time):
        '''
        Updates the values about the system load. Values are updated only once
        a minute or less, as the load is measured with granularities of 1, 5
        and 15 minutes 
        
        :type cur_time: floating point, as returned by time.time()
        '''
        if cur_time - self.last > 60.0:
            # nothing happens if this method
            # is invoked more than once in a minute
            self.counter += 1L
            self.last = cur_time
            row = []
            row.append(self.counter)
            row.append('%.2f' % (cur_time - self.get_creation_time()))
            for load in os.getloadavg():
                row.append('%.2f' % load)
            self.writer.writerow(row)
            

class NetworkRate(Monitor):
    '''
    Monitors the network rate (IN and OUT
    '''
    
    def __init__(self, path=NET, msg=None):
        Monitor.__init__(self, path, buffering=1024)
        
        self.last = self.get_creation_time()
        
        self.f.write('# Network in/out, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, KB/s (in), KB/s (OUT)\n')
        if msg != None:
            self.f.write('# %s' % msg)
            
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        row = []
        row.append('# event')
        row.append('time')
        row.append('kb_in')
        row.append('kb_out')
        self.writer.writerow(row)
        
        self.counter = 0L
        
        self.last_r = 0L
        self.last_t = 0L
        
        uname = os.uname()[0]    
        if uname == 'Darwin':
            self.iface = 'en0'
            self.mac_os_x = True
        elif uname == 'Linux':
            self.iface = 'eth0'
            self.mac_os_x = False
        
        
    def parse_proc_net_dev(self):
        '''
        Gets the number of received and transmitted bytes on Linux
        - iface: the interface, e.g., eth0
        '''
        f = open('/proc/net/dev')
        r = 0
        t = 0
        for l in f:
            if l.find("%s:" % self.iface) == -1: continue
            spl = l.split()
            r, t = atol(spl[1]), atol(spl[9])
        f.close()
        return r, t

            
    def parse_netstat(self):
        '''
        Gets the number of received and transmitted bytes on Mac OS X
        - iface: the interface, e.g., en0
        '''
        # mac os 10.6
        output = subprocess.check_output(['netstat', '-b', '-I', self.iface], stderr=subprocess.STDOUT)
        tmp = string.split(output, '\n')
        res = shlex.split(tmp[1], comments=False) # 2nd line
        r, t = atol(res[6]), atol(res[9])
        return r, t
        
        
        
    def update(self, cur_time):        
        if self.mac_os_x == True:
            r, t = self.parse_netstat()
        else:
            r, t = self.parse_proc_net_dev() 
            
        now = cur_time
        delta = now - self.last
        rate_r = ((r - self.last_r) / delta) / 1024.0
        rate_t = ((t - self.last_t) / delta) / 1024.0
        self.last = now
        self.last_r = r
        self.last_t = t
        
        if (self.counter > 0L):
            row = []
            row.append(self.counter)
            row.append('%.2f' % (now - self.get_creation_time()))
            row.append('%.2f' % rate_r)
            row.append('%.2f' % rate_t)
            self.writer.writerow(row)
        
        self.counter += 1L
        self.last = cur_time
    
    

class ArrivalRate(Monitor):
    '''
    Monitors the arrival rate
    '''
    
    def __init__(self, path=ARR_RATE, msg=None):
        Monitor.__init__(self, path)
        
        self.last_time = self.get_creation_time()
        
        self.counter = 0
        self.last_rate = 0.0
        self.last_total = 0 # last value of 'stot'
        
        self.f.write('# Arrival rate, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, arr. rate\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        if msg != None:
            self.f.write('# %s' % msg)
            
        row = []
        row.append('# event')
        row.append('time')
        row.append('arr_rate')
        self.writer.writerow(row)
            
            
    def update(self, cur_total, cur_time):
        '''
        Writes the last arrival rate (req/sec) to file. This object keeps track
        of the time this method was last invoked, so the update method can be 
        invoked at any time. The arrival rate is normalized in number of req/sec.
        
        :type cur_total: int
        :param cur_total: the current total number of jobs arrived
        :type cur_time: float, see time.time()
        :rtype: float. Returns the current arrival rate.
        '''
        if self.last_total > cur_total:
            raise UserWarning('cur_aggregate (%d) < last_total (%d)!' % (cur_total, self.last_total))
        
        delta_val = cur_total - self.last_total
        rate = delta_val / (cur_time - self.last_time) # computes the arr. rate.
        
        if rate > 1.0:
            # log and update stats only if the arr rate is > 1 job/sec
            self.last_total = cur_total
            self.last_rate = rate
            self.last_time = cur_time
            
            self.counter += 1L
            if self.counter > 1:
                row = []
                row.append(self.counter)
                row.append('%.2f' % (cur_time - self.get_creation_time()))
                row.append('%.2f' % self.last_rate)
                self.writer.writerow(row)
                
        return rate

        
        
    def get_arr_rate(self):
        return self.last_rate
        
    def reset(self):
        '''
        Resets the value of last_total.
        This method should be called when HAProxy is restarted/reloaded,
        as the new process resets the statistics.
        '''
        self.last_total = 0
        
        
class Cost(Monitor):
    '''
    Monitors the number of jobs in the system, number of active servers, and 
    cost
    '''
    
    PORTION_LEN = 360
    
    def __init__(self, holding_cost, server_cost, path=COST, msg=None):
        '''
        Initializer
            * param holding_cost: the holding cost ($ per job/second)
            * type holding cost: float
            * param server_cost: the cost per server ($/second)
            * type server_cost cost: float
            * param path: path to the file. Default value 'cost.csv'
            * type path: string
            * param msg: The message to write. Default None
            * type msg: string
        '''  
        Monitor.__init__(self, path)
        
        self.f.write('# Cost function, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        self.f.write('# c1 = %.3f, c2 = %.3f\n' % (holding_cost, server_cost))
        if msg != None:
            self.f.write('# %s' % msg)
        
        #self.f.write('# Event no., relative time, arr. rate, no. of jobs, servers consuming power, servers running jobs, cost, avg. cost, total cost\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        
        row = []
        row.append('# event')
        row.append('time')
        row.append('req_rate')
        row.append('jobs')
        row.append('servers_on')
        row.append('servers_run')
        row.append('cost')
        row.append('avg_cost')
        row.append('tot_cost')
        row.append('m')
        row.append('D')
        row.append('U')
        self.writer.writerow(row)
        
        self.counter = 0L
        
        self.last = self.get_creation_time()
        
        self.holding_cost = holding_cost    # c1
        self.server_cost = server_cost      # c2
        self.counter = 0
        
        self.total_cost = 0.0   # total cost
        self.avg_cost = 0.0 # average cost. updated at every call of update as
        # well as at the end
        
        self.costs = [] # array of costs, used to compute confidence intervals
        
        
    def update(self, jobs, powered_on_servers, active_servers, cur_time, arr_rate, reserves):
        '''
        Updates the log and computes the cost.
        powered_on_servers includes the servers in POWERING_ON state, so the
        invariant powered_on_servers >= active_servers always hold.

        * param jobs: the number of jobs in the system
        * type jobs: int
        * param active_servers: the number of active servers
        * type active_servers: int
        * param running servers: no. of servers running jobs
        * type running: int
        * param cur_time: the current time
        * type cur_time: float
        * param arr_rate: the arrival rate
        * type arr_rate: float
        * param reserves: the reserves
        * type reserves: anor.commons.reserves
        * rtype: None
        
        
        The no. of jobs and active servers are of type int!!!
        '''

        if active_servers > powered_on_servers:
            raise ValueError('powered_on_servers < active servers, %d, %d' % 
                             (powered_on_servers, active_servers))

        self.counter += 1
        delta = cur_time - self.last
        self.last = cur_time
        
        # write only if something happened
        if jobs > 0 or powered_on_servers > 0:
            row = []
            row.append(self.counter)
            row.append('%.2f' % (cur_time - self.get_creation_time()))
            row.append('%.3f' % arr_rate)
            row.append(jobs)
            row.append(powered_on_servers)
            row.append(active_servers)
            
            # compute cost
            cost = delta * (jobs * self.holding_cost + powered_on_servers * self.server_cost)
            self.total_cost += cost
            self.avg_cost = self.total_cost / (self.last - self.get_creation_time())
            
            row.append('%.3f' % cost)
            row.append('%.3f' % self.avg_cost)
            row.append('%.1f' % self.total_cost)
            row.append('%d' % reserves.m)
            row.append('%d' % reserves.D)
            row.append('%d' % reserves.U)
            self.writer.writerow(row)
            self.f.flush()
            
        if self.counter % self.PORTION_LEN == 0: # used to compute confidence intervals
            self.costs.append(self.total_cost)
            
            
    def close(self):
        # total cost / time
        delta =  self.last - self.get_creation_time()
        if self.total_cost > 0.0 and delta > 0.0:
            avg_cost = self.total_cost / delta
            ci = self.compute_conf_int()
            print ci
            self.f.write('# total cost %.3f $, avg. cost %.3f $/sec\n' 
                         % (self.total_cost, avg_cost))
            self.f.write('# 0.95 conf. int. %.3f\n' % ci)
        Monitor.close(self)
        
        
    def compute_conf_int(self, ci=0.95):
        import math
        
        portions = len(self.costs) # no. of portions
        
        if portions < 8:
            print 'Not enough portions'
            return 0.0
        
        for i in xrange(portions-1, 0, -1):
            self.costs[i] -= self.costs[i-1] # portion revenues
            
        for i in xrange(0, portions):
            self.costs[i] /= self.PORTION_LEN   # per unit time
            
        avg = self.avg_cost
        sd = 0.0
        for i in xrange(0, portions):
            sd += (self.costs[i] - avg)**2
        sd = math.sqrt(sd / (portions -1.0))
            
        # 95% conf. int
        ci = 2.2281389 * sd / math.sqrt(portions -1)
        return ci
       
       
class HAProxy(Monitor):
    '''
    Monitors the status of HAproxy
    '''
    
    def __init__(self, path=HAPROXY, msg=None):
        Monitor.__init__(self, path)
        
        self.f.write('# HAProxy status, created on {0}\n'.format(time.ctime(self.get_creation_time())))
        #self.f.write('# Event no., time, qcur, act, scur, req_rate, req_tot, ')
        #self.f.write('bytes_in, bytes_out, req_err, conn_err, resp_err,')
        #self.f.write('hrsp_1xx, hrsp_2xx, hrsp_3xx, hrsp_4xx, hrsp_5xx, ')
        #self.f.write('hrsp_other, cli_abrt, srv_abrt\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        
        row = []
        row.append('# event')
        row.append('time')
        row.append('qcur')
        row.append('act')
        row.append('scur')
        row.append('req_rate')
        row.append('req_tot')
        row.append('bytes_in')
        row.append('bytes_out')
        row.append('req_err')
        row.append('conn_err')
        row.append('resp_err')
        row.append('hrsp_1xx')
        row.append('hrsp_2xx')
        row.append('hrsp_3xx')
        row.append('hrsp_4xx')
        row.append('hrsp_5xx')
        row.append('hrsp_other')
        row.append('cli_abrt')
        row.append('srv_abrt')
        self.writer.writerow(row)
        
        
        self.counter = 0L
        if msg != None:
            self.f.write('# %s' % msg)
    
    
    
    def update(self, frontend, cur_time):
        '''
        Writes the current statistics state to file
        :type stat: dictionary, see HAPROXY_STAT_CSV in socket_haproxy for the keys
        :param frontend The statistics about the frontend
        :type cur_time: float, see time.time()
        '''
        self.counter += 1L
        row = []
        row.append(self.counter)
        row.append('%.2f' % (cur_time - self.get_creation_time()))
        for val in HAPROXY_STAT_LOG:
            row.append('%d' % (frontend[val]))
        
        self.writer.writerow(row)
        
        
class All():
    
    
    def __init__(self, costs):
        self.mem = Memory()
        self.conn = Connections()
        self.cpu = Cpu()
        self.load = Load()
        self.net = NetworkRate()
        self.arr_rate = ArrivalRate()
        self.haproxy = HAProxy()
        self.cost = Cost(costs.c1, costs.c2)
        
        
    def update_cost(self, jobs, powered_on_servers, active_servers, cur_time, 
                    arr_rate, reserves):
        '''
            Updates the cost.
            * param jobs: no. of jobs in the system
            * param powered_on_servers: no. of servers consuming power
            * param active_servers: no. of servers running jobs
            * param cur_time: the current time
            * type cur_time: float
            * param arr_rate: the arrival rate (req/second)
            * type arr:=_rate: float            
            * param reserves: the reserves
            * type reserves: anor.commons.reserves
            * rtype: None
        '''
        self.cost.update(jobs, powered_on_servers, active_servers, cur_time, 
                         arr_rate, reserves)
        
        
    def update_memory(self, cur_time):
        self.mem.update(cur_time) 


    def update_connections(self, cur_time):
        self.conn.update(cur_time)
        
    def update_cpu(self, cur_time):
        self.cpu.update(cur_time)
        
    def update_load(self, cur_time):
        self.load.update(cur_time)
            
    def update_network(self, cur_time):
        self.net.update(cur_time)
        
        
    def update_hw(self, cur_time):
        self.update_memory(cur_time)
        self.update_connections(cur_time)
        self.update_cpu(cur_time)
        self.update_load(cur_time)
        self.update_network(cur_time)
        
    
    def update_arr_rate(self, cur_aggregate, cur_time):
        '''
        * type cur_aggregate: int
        * param cur_aggergate: the total number of arrivals
        * param cur_time: The current time, in seconds
        * type cur_time: flot
        * return: the arrival rate
        * rtype: float
        '''
        return self.arr_rate.update(cur_aggregate, cur_time)
        
    def update_haproxy(self, backend, cur_time):
        self.haproxy.update(backend, cur_time)
        
        
    def reset_arr_rate(self):
        self.arr_rate.reset()
        
        
    def get_arr_rate(self):
        return self.arr_rate.get_arr_rate()
        
        
    def get_avg_cost(self):
        return self.cost.avg_cost
    
    def get_total_cost(self):
        return self.cost.total_cost
        
    def close_all(self):
        self.mem.close()
        self.conn.close()
        self.cpu.close()
        self.load.close()
        self.net.close()
        self.arr_rate.close()
        self.haproxy.close()
        self.cost.close()
    
if __name__ == "__main__":
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.INFO)
        
    cpu = Cpu()
    load = Load()
    conn = Connections()
    net = NetworkRate()
    mem = Memory()
    
    arr_rate = ArrivalRate()
    
    time.sleep(2)
    while 1:
        try:
            print 'update'
            cur_time = time.time()
            cpu.update(cur_time)
            load.update(cur_time)
            net.update(cur_time)
            conn.update(cur_time)
            mem.update(cur_time)
            
            time.sleep(2)
        except KeyboardInterrupt:
            cpu.close()
            load.close()
            net.close()
            conn.close()
            mem.update()        
            break
    
