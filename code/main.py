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
Created on Feb 27, 2012

@author: michele

Main script. This is to be run on the HAProxy host.
All the servers have the same tag. The program keeps track
of which machine is marked as a reserve and which one is not by means of two lists.
This enables one to dynamically change the number of reserves without needing
to query EC2 to retrieve the tags.
'''


import logging, os, time, sys, signal
from socket import error as SocketError

import monitor.commons as utils
import monitor.haproxy_configuration as haproxy_configuration
import monitor.stats as stats
import monitor.socket_haproxy as socket_haproxy
from anor.commons import Reserves, Load, Costs

import argparse
from anor.algorithms import Heuristic


# ------------------------------------------------------------------------- #
#                               GLOBALS                                     #
# ------------------------------------------------------------------------- #

# The configuration file
haproxy_conf_file = "/etc/haproxy/haproxy.cfg"

ENABLE = 'enable'
DISABLE = 'disable'


# Amazon EC2 credentials
aws_access_key_id = 'your key id here'
aws_secret_access_key = 'your key here'



'''
All running instances have the tag with key 'wikipedia':
    * The load balancer has value 'haproxy'
    * Apache servers have value 'apache'
'''
TAG_KEY = 'wikipedia'
TAG_VALUE_APACHE = 'apache'
TAG_VALUE_RESERVE = 'reserve'


PATH_PID_FILE = '/tmp/monitor_haproxy.pid'


ON = 'ON'
OFF = 'OFF'
POWERING_ON = 'POWERING_ON'


log = logging.getLogger('ec2_reserves')

def load_lambdas(path):
    '''
    Load the file with the arrival rates (Oracle)
    '''
    log.info('Loading the lambdas')
    lines = []
    with open(path) as in_file:
        for tmp in in_file.readlines():
            if tmp.startswith('#'):
                continue
            y = [value for value in tmp.split()]
            lines.append(float(y[0]))
    return lines


class ArrRate():
    '''
    Object used to monitor the arrival rate. It is used ONLY when reconfiguring
    the number of reserves
    '''
    
    def __init__(self):
        self.arrivals = 0
        self.time = time.time()
        
        
    def update(self, cur_arrivals):
        '''
        Updates the internal state and returns the current arrival rate (req/sec).
            * type cur_arivals: int
            * param cur_arrivals: the current number of arrivals
            * rtype: float
        '''
        now = time.time()
        rate = (cur_arrivals - self.arrivals) / (now - self.time)
        self.time = now
        self.arrivals = cur_arrivals
        return rate


class Monitor():
    '''
    Class used to control servers on Amazon EC2 cloud. The reserves block
    is 'powered' up/down by means of a TAG.
    '''


    def __init__(self, reserves, costs, mu, cores, power_up_time, monitor_interval, 
                 reconf_interval, lambdas_path, enable_tresholds):
        '''
        Initializes the class. Then it fetches the details of the 
        `ALWAYS-ON' servers from Amazon EC2, updates the configuration of
        HAProxy, and reloads it.
        
        
        * type reserves: commons.Reserves
        * param reserves: the reserves (number and thresholds)
        * type costs: anor.commons.Costs
        * param costs: The holding cost and the cost for servers
        * type mu: float
        * param mu: service rate
        * type cores: int
        * param cores: number of cores per server
        * type power_up_time: float
        * param power_up_time: the average time (in seconds) required to power
            up the reserves
        * type monitor_interval: float
        * param monitor_interval: how often should HAProxy be monitored?
            Default 5 seconds
        * type reconf_interval: int
        * param reconf_interval: how often should the system reconfigure the
            parameters? Default 300 seconds. If 0, ne reconfiguration occurs
        * type enable_tresholds: boolean
        * param enable_tresholds: enable D and U? [deafult True]
        '''
        self.costs = costs # holding cost and cost for servers
        self.mu = mu
        self.monitor_interval = monitor_interval
        self.reconf_interval = reconf_interval
        self.cores = cores
        self.enable_tresholds = enable_tresholds
        if self.enable_tresholds == False:
            log.info('Tresholds disabled')
        
        self.all_stats = stats.All(costs)
        self.__power_up_time = power_up_time # in seconds, float
        self.res = reserves
            
        self.servers = utils.InstanceList()
        self.__init_list()
        self.N = self.servers.size()
        
        # adds ALL the servers to the configuration file, and reloads HAProxy
        self.__reload_haproxy()
        
        self.__res_state = OFF # status of the reserves
        
        self.__go = True # guard used in the for loop
        signal.signal(signal.SIGTERM, self.do_exit)
        signal.signal(signal.SIGINT, self.do_exit) # keyboard interrupt       
        
        self.socket = socket_haproxy.sock()
        self.data = None # data attached to the socket        
        self.arr_rate = ArrRate()
        
        # No. of reconfigurations
        self.epochs = 0
        
        # Oracle code
        if lambdas_path is None:
            self.oracle = False
        else:
            self.oracle = True
            # load the traces
            log.debug("Loading lambdas, using oracle")
            self.lambdas = load_lambdas(lambdas_path)
            # select only 24 hours, day 11, indexes 243:267
            #self.lambdas = self.lambdas[243:277] # take 10 extra hours
            self.lambdas[:] = [x * 1.5 for x in self.lambdas] # scale up the load by 50%
            
        
    
    def do_exit(self, sig, stack):
        '''
        Clean exit
        '''
        # signal # 2 is SIGINT, see man signal
        log.info("Received exit signal")
        self.__go = False
        
        
    def __init_list(self):
        '''
        Initializes the list with the servers which are always on
        '''
        conn = utils.create_ec2_connection(aws_access_key_id, aws_secret_access_key)
        apache_filter = utils.create_filter(key=TAG_KEY, value=TAG_VALUE_APACHE)
        reservations = conn.get_all_instances(filters=apache_filter)
        instances = [i for r in reservations for i in r.instances]
        
        
        if len(instances) == 0:
            log.info("No apache servers found")
        elif self.res.m > len(instances):
            raise ValueError('reservers (%d) > available servers (%d)!!' %
                             (self.res.m, len(reservations)))
        else:
            
            for i in range(self.res.m):
                tmp = instances[i]
                log.info("Adding %s, IP %s to reserves", tmp.id, tmp.ip_address)
                
                self.servers.add(utils.Instance(tmp, utils.RESERVE))
            for i in range(self.res.m, len(instances)):
                # http://boto.s3.amazonaws.com/ec2_tut.html
                tmp = instances[i]
                log.info("Adding %s, IP %s to always on", tmp.id, tmp.ip_address)
                self.servers.add(utils.Instance(tmp, utils.ALWAYS_ON))
                
        del conn
        
        
   
    def enable_disable_reserves_haproxy(self, enable=ENABLE):
        '''
        Enables/disables reserves the servers
         * type servers_list: list of strings
         * param enable: either 'enable' or 'disable', or a ValueError will be
                         raised
         * type enable: string (either 'enable' or 'disable')
         * rtype: void
        '''
        # If it keeps making troubles,
        # use echo "set weight www/i-cef598a9 0%" | socat unix-connect:/tmp/haproxy stdio
        # to disable, and set weight to 100% to enable (the light on the web page stays green)
        if enable not in ['enable', 'disable']:
            raise ValueError('Expecting either enable or disable, got %s' % enable)
       
        #weight = 100
        #if enable == DISABLE:
        #    weight = 0
       
        #l = []
        for i in self.servers.values():
            if i.state == utils.RESERVE:
                command = '%s server www/%s' % (enable, i.instance_id)
                #tmp = 'set weight www/%s %d%%' % (i, weight)
                #l.append(tmp)
                try:        
                    self.data.socket.send(command)
                    self.data.socket.wait()
                    
                    if log.isEnabledFor(logging.DEBUG):
                        log.debug(command)
                except SocketError, e:
                    log.error('socket error, unable to enable/disable servers: %s' % e)
                    self.data.reconnect()
                
                
        #command = ';'.join(l)
        
        
        
    def check_result(self, enable, command):

        expected = self.N
        if enable == DISABLE:
            expected = expected - self.res.m
            
        log.info("enable? %s, expected %d" % (enable, expected))


        # check
        success = False
        while not success:
            try:        
                self.data.socket.send(command)
                self.data.socket.wait()
                
                if log.isEnabledFor(logging.DEBUG):
                    log.debug(command)
            except SocketError, e:
                log.error('socket error, unable to enable/disable servers: %s' % e)
                self.data.reconnect()
                continue
            
            # double check that the number or servers is correct
            self.data.update_stat()
            backend = self.data.stat[2]["BACKEND"]
                
            # no. of active servers
            active_servers = backend['act']
            
            reserves = []
            always_on = []
            
            for i in self.servers.values():
                if i.state == utils.ALWAYS_ON:
                    always_on.append(i.instance_id)
                elif i.state == utils.RESERVE:
                    expected -= 1
                    reserves.append(i.instance_id)
                else:
                    msg = 'Unexpected state [%d] for instance %s' % (i.state, i.instance_id)
                    log.fatal(msg)
                    raise RuntimeError(msg)
            
            if active_servers == expected:
                success= True
            else:
                msg = "Expected %d active servers, have %d. Command: %s" % (expected, active_servers, command)
                log.critical(msg)
                msg = 'Always on: '
                for val in always_on:
                    msg += val + ' '
                log.critical(msg)
                
                msg = 'Reserves: '
                for val in reserves:
                    msg += val + ' '
                log.critical(msg)
                # try to sleep 0.1 sec before executing the operation again
                time.sleep(0.1) 
                
                log.warn('Recreating UNIX socket')
                try:
                    self.socket = socket_haproxy.sock()
                    self.data = socket_haproxy.SocketData(self.socket) # socket_path is used to reconnect
                    # the 2 means BACKEND, see documentation (sec. 9.2)
                    filter_backend = ['-1 2 -1']
                    self.data.register_stat_filter(filter_backend)
                    self.socket.connect()
                    log.info('Socket connected')
                    
                    self.__recovery(always_on, reserves, enable) # trying to recovery
                    success = True
                except SocketError, e:
                    log.fatal('unable to reinitialize: %s' % e)
                    sys.exit(1)
                    
        return success
                                  
                                  
    
    def __recovery(self, always_on, reserves, enable_disable_reserves):
        '''
        Try to perform recovery. Set all the always on servers to ON,
        and the reserves to the expected state
        '''
        
#        weight = 100
#        if enable_disable_reserves == DISABLE:
#            weight = 0
        
        log.warn('Recovery')
        l = []
        for i in always_on:
            tmp = 'enable server www/%s' % i
            #tmp = 'set weight www/%s 100%%' % (i)
            l.append(tmp)
     
        command = ';'.join(l)
        try:        
            self.data.socket.send(command)
            self.data.socket.wait()
            
            if log.isEnabledFor(logging.DEBUG):
                log.debug(command)
        except SocketError, e:
            log.error('socket error, unable to enable always on servers: %s' % e)
            self.data.reconnect()

        del l        
        l = []
        for i in reserves:
            tmp = '%s server www/%s' % (enable_disable_reserves, i)
            #tmp = 'set weight www/%s %d%%' % (i, weight)
            l.append(tmp)
        command = ';'.join(l)
        try:        
            self.data.socket.send(command)
            self.data.socket.wait()
            
            if log.isEnabledFor(logging.DEBUG):
                log.debug(command)
        except SocketError, e:
            log.error('socket error, unable to enable/disable reserves: %s' % e)
            self.data.reconnect()
            
            
        self.data.update_stat()
        backend = self.data.stat[2]["BACKEND"]
            
        # no. of active servers
        active_servers = backend['act']
        expected = len(always_on)
        if enable_disable_reserves == 'enable':
            expected += len(reserves)
        
        if active_servers != expected:
            msg = "[Recovery] Expected %d active servers, have %d. Command: %s" % (expected, active_servers, command)
            log.fatal(msg)
            sys.exit(1)
            
            
    def __disable_reserves(self):
        '''
        Disables the reserves, see 9.2
        http://haproxy.1wt.eu/download/1.4/doc/configuration.txt
        '''
        self.enable_disable_reserves_haproxy('disable')
        self.set_res_state(OFF)
            
    
    # handler for SIGALRM signals
    def __enable_reserves(self, signum, stack):
        '''
        Enables the reserves, see 9.2
        http://haproxy.1wt.eu/download/1.4/doc/configuration.txt
        '''
        
        if self.res.m > 0:
            self.data.update_stat()
            backend = self.data.stat[2]["BACKEND"]
            # current number of jobs inside the system (waiting or being executed)
            scur = backend['scur']
            if scur <= self.res.D:                
                self.set_res_state(OFF) # set the state of reserves to OFF
                log.info('scur %d, switched state from POWERING_ON to OFF' % scur)
            else:                    
                self.enable_disable_reserves_haproxy()
                self.set_res_state(ON)
                log.info('scur %d, switched state from POWERING_ON to ON' % scur)
            
        
        
    def get_res_state(self):
        '''
        Gets the state of the reserves
        :rtype: string (ON, OFF, POWERING_ON)
        '''
        return self.__res_state
        
        
    def set_res_state(self, new_state):
        '''
        Sets the state of the reserves to the specified state
        :type new_state: string
        :param new_state: ON, OFF, or POWERING_ON
        '''
        if new_state not in [ON, OFF, POWERING_ON]:
            raise ValueError('The state should be either ON, OFF, or POWERING_ON')
        
        self.__res_state = new_state
    
    
    def sleep(self, sleep_time=None):
        if sleep_time == None:
            sleep_time = self.monitor_interval
        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt: # CTRL+D
            self.__go = False
            log.info('Keyboard interrupt')
            

                
    def change_allocation(self):
        '''
        Gets the arrival rate and creates the thread that computes the
        new number of reserves and corresponding threshold 
        '''        
        backend = self.data.stat[2]['BACKEND']; # dictionary
        # total no. of jobs
        scur = backend['stot']
        lam = self.arr_rate.update(scur)
        log.info('Estimated arr. rate: %.3f' % lam)    
        
        if self.oracle:
            arr_rate = self.lambdas[self.epochs]
            log.info("[Oracle] Setting lambda to %.3f" % arr_rate)    
            lam = arr_rate
            
        if lam > 0.0:
            log.info("Arr rate %.3f" % lam)
            # executes reconfiguration in a separate thread
            #self.worker_process = Thread(name='reconfigure', target=self.worker, args=(lam,))
            #self.worker_process.setDaemon(True)
            #self.worker_process.start()
            nu = 1.0 / self.__power_up_time
            load = Load(lam, self.mu)
            heuristic = Heuristic(self.N * self.cores, nu, self.costs.c1, self.costs.c2, self.cores)
            solution = heuristic.heuristic(load)
            new_reserves = solution.reserves
            new_reserves.m /= self.cores               
            
            log.info('Current configuration, %s, new solution: %s' 
                     % (self.res.__str__(), solution.__str__()))            

            diff = self.res.m - new_reserves.m
            if diff == 0:
                log.info("Nothing to do, old reserve parameters equal to the new ones")
                return
            
            always_on = []
            reserves = []
            if diff > 0: # move some reserves to always_on
                for i in self.servers.values():
                    if i.state == utils.ALWAYS_ON:
                        always_on.append(i.instance_id)
                    elif i.state == utils.RESERVE and diff > 0:
                        i.state = utils.ALWAYS_ON
                        diff -= 1
                        always_on.append(i.instance_id)
                    else:  # state = RESERVE
                        reserves.append(i.instance_id)
                    
            else: # move some always on servers to reserves
                for i in self.servers.values():
                    if i.state == utils.RESERVE:
                        reserves.append(i.instance_id)
                    elif i.state == utils.ALWAYS_ON and diff < 0:
                        i.state = utils.RESERVE
                        diff += 1
                        reserves.append(i.instance_id)
                    else:
                        always_on.append(i.instance_id)
                        
            # fix the servers that have been moved
            if self.__res_state == ON:
                self.__recovery(always_on, reserves, 'enable')
            else:
                self.__recovery(always_on, reserves, 'disable')
            
            # the tresholds might have changed
            self.res = new_reserves

    
   
                  
    
    def monitor_haproxy(self):
        '''
        Monitors the status of HAProxy, adding/removing reserves
        according to the number of jobs in the system.
        This function uses the SIGALRM signal to be notified when the reserves
        become available. 
        '''
        
        pid = os.getpid() # get process id
        log.info("PID # %d" % pid)
        with open(PATH_PID_FILE, 'w') as pid_file:
            pid_file.write('%d\n' % pid)
        
        try:
            self.data = socket_haproxy.SocketData(self.socket) # socket_path is used to reconnect
            # the 2 means BACKEND, see documentation (sec. 9.2)
            filter_backend = ['-1 2 -1'] 
            self.data.register_stat_filter(filter_backend)
            self.socket.connect()
            log.info('Socket connected')
            
            # disable reserves
            self.__disable_reserves()
            
            last_check = time.time()
            self.sleep()
            
            next_reconfiguration_at = 0.0
            if self.reconf_interval > 0:
                #self.t.start()
                next_reconfiguration_at = time.time() + self.reconf_interval
            
            # set first allocation, if using oracle predictor
            if self.oracle:
                self.data.update_stat()
                log.info("Oracle, setting first allocation")
                self.change_allocation()
            self.epochs = 1
                
            log.info("Entering while loop")
            while self.__go:              
                cur_time = time.time() # get current time
                
                # update stats
                try:
                    self.data.update_stat()
                except RuntimeError, e:
                    log.error(e)
                    self.data.reconnect()
                    self.data.update_stat()
                    
                stat = self.data.stat;
                backend = stat[2]["BACKEND"] # dictionary, 2 is the key (see filter_backend)
                
                # Check if reconfiguration is necessary 
                if self.reconf_interval > 0 and cur_time > next_reconfiguration_at:
                    self.change_allocation()    
                    self.epochs += 1
                    next_reconfiguration_at = cur_time + self.reconf_interval
                
                # current number of jobs inside the system (waiting or being executed)
                scur = backend['scur']
                # no. of active servers
                active_servers = backend['act']
                # total number of jobs that went through the system from time 0
                tot_sessions = backend['stot']
                # arr. rate
                arr_rate = self.all_stats.update_arr_rate(tot_sessions, cur_time)
                # how about using 'req_rate' from HAProxy instead?
                
                
                self.all_stats.update_hw(cur_time)
                # haproxy stats
                self.all_stats.update_haproxy(backend, cur_time)
                
                # deal with reserves
                powered_on_servers = active_servers
                if self.get_res_state() == POWERING_ON:
                    # reserves being powered on consume power
                    powered_on_servers = self.N # always on + reserves
                
                # update cost
                self.all_stats.update_cost(scur, powered_on_servers * self.cores, 
                                           active_servers * self.cores, 
                                           cur_time, arr_rate, self.res)    
                
                if log.isEnabledFor(logging.DEBUG) and (scur > 0 or powered_on_servers > 0):
                    delta = cur_time - last_check                    
                    # cost
                    cost = delta * (scur * self.costs.c1 + powered_on_servers * self.costs.c2 * self.cores)
                    log.debug('L=%d, ON=%d, ACT=%d, C=%.3f, lam=%.1f' 
                                % (scur, powered_on_servers, active_servers, cost, arr_rate))
             
                
                # check no. of jobs in the system and enable/disable
                # reserves, if necessary
                if self.enable_tresholds == True:
                    if scur > self.res.U and self.res.m > 0 and self.get_res_state() == OFF:
                        
                        power_up_delay = utils.exp_deviate(self.__power_up_time)
                        log.info("scur = %d, enabling reserves in %.2f sec." % (scur, power_up_delay))
                        self.set_res_state(POWERING_ON)
                        
                        # set alarm
                        signal.signal(signal.SIGALRM, self.__enable_reserves)
                        signal.setitimer(signal.ITIMER_REAL, power_up_delay)
                    
                    elif scur <= self.res.D and self.res.m > 0 and self.get_res_state() == ON:
                        log.info('scur %d, disabling reserves' % scur)
                        self.__disable_reserves()                    
                    
                last_check = cur_time # update the time when the last check was made   
                
                # wait before the new cycle 
                sleep_interval = self.monitor_interval - (time.time() - cur_time)
                if sleep_interval > 0.0:
                    self.sleep(sleep_interval)                    
        except SocketError, e:
            log.error('socket error: %s' % e)
            sys.exit(1)
        #except Exception, e:
        #    print e
        #    raise e
        finally:
            self.socket.close() # close socket
            self.all_stats.close_all() # close files attached to the statistics
                
            log.info("Total cost %.3f, avg. %3f" % 
                     (self.all_stats.get_total_cost(),
                      self.all_stats.get_avg_cost()))
            
            # cleanup
            if os.path.exists(PATH_PID_FILE):
                try:
                    os.remove(PATH_PID_FILE)
                except IOError:
                    # ignore
                    pass
                
            log.info("Exiting...")
        
    
    def __reload_haproxy(self):
        '''
        Reloads HAProxy
        '''    
        
        #merged = self.__always_on_list.get_running_servers()[:]
        #for i in self.__reserves_list.get_running_servers():
        #    merged.append(i)
        
        haproxy_configuration.update_haproxy_config(haproxy_conf_file, 
                                        self.servers.values())
        
        if os.uname()[0] == haproxy_configuration.MAC_OS:
            log.info("Config file is %s" % haproxy_conf_file)
            haproxy_configuration.reload_haproxy(haproxy_conf_file)
        else:
            haproxy_configuration.reload_haproxy()
    
        
if __name__ == '__main__':
    print 'starting at %s' % time.asctime()
    utils.check_if_sudo()    
    
    #FORMAT = '%(asctime)s %(levelname)-8s %(message)s'
    FORMAT = '[%(asctime)s] - [%(levelname)8s] -- %(message)s'
    
    
    logging.basicConfig(format=FORMAT, level=logging.INFO)
    #logging.basicConfig(format=FORMAT, level=logging.INFO, filemode='w',
    #                    filename='monitor.log')
    
    #console = logging.StreamHandler()
    #console.setLevel(logging.INFO)
    #console.setFormatter('%(asctime)s %(message)s')
    #logging.getLogger('').addHandler(console)
    
    
    # sudo python monitor.py -mu 10 -m 0 -D 0 -U 0 -c1 1.0 -c2 1.0
    parser = argparse.ArgumentParser(description='HAProxy monitor')
    parser.add_argument('-mu', type=float, required=False, default=4.35,
                        help='Service rate [default 4.35]')
    parser.add_argument('-m', type=int, required=True, help='Number of reserves')
    parser.add_argument('-D', type=int, required=True, help='Lower threshold')
    parser.add_argument('-U', type=int, required=True, help='Upper threshold')
    parser.add_argument('-c1', type=float, required=False, default=1.2,
                        help='Holding cost (default 1.2)')
    parser.add_argument('-c2', type=float, required=False, default=1.0,
                        help='Server cost (default 1.0)')
    parser.add_argument('-p', type=float, required=False, default=60.0,
                        help='Avg. # of sec. required to power up reserves [default 60]')
    parser.add_argument('-mon', type=int, required=False, default=1,
                        help="Monitoring interval, in seconds [default 1]")
    parser.add_argument('-r', type=int, required=False, default=3600,
                        help="Reconfiguration interval, in seconds [default 3600]")
    parser.add_argument('-co', type=int, required=False, default=2,
                        help='No. of cores per server [default 2]')
    parser.add_argument('-o', required=False, default=None, 
                        help = "file with load trace")
    parser.add_argument('-t', required=False, default='True',
                        help = 'Enable tresholds? [Default True, applies only if -r > 0]')
    args = parser.parse_args()
    
    if args.r == 0.0:
        log.info("Reconfiguration disabled")
    else:
        log.info("Reconfiguration interval %d seconds" % args.r)
        
    if args.o is not None:
        log.info('Using oracle, load trace is %s' % args.o)
       
    
    tresholds_enabled = False 
    if args.t == 'True':
        tresholds_enabled = True
        
    log.info("Power up delay %d sec." % args.p)
    log.info('Treshold enabled: %s' % tresholds_enabled)
       
    costs = Costs(args.c1, args.c2)
    reserves = Reserves(args.m, args.D, args.U)
    monitor = Monitor(reserves, costs, args.mu, args.co, args.p, args.mon, 
                      args.r, args.o, tresholds_enabled)
    monitor.monitor_haproxy()
       
