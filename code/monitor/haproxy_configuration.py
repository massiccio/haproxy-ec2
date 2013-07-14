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
Created on Feb 7, 2012

@author: michele
'''


import os # for reloading haproxy configuration via command line
import re
from shutil import move, copystat
from tempfile import mkstemp
import logging

import commons as utils


# max connections
MAX_CONN = 2

# apache port
APACHE_PORT = 80

# File where the pid is written
PID_FILE = '/var/run/haproxy.pid'

s_line = re.compile("^\\s*server\\s+.*$")

log = logging.getLogger('ec2_reserves')

# the server name is the instance-id

def update_haproxy_config(path_conf_file, list_running=None, path_new_file=None):
    '''
    Parses the configuration file specified by the path parth_conf_file
    and adds the servers included into the set passed as a second parameter
    The last parameter is the path where the new configuration file is saved.
    If null, the path of the input file is employed.
    
    :type list_running: List of type ec2_reserves.Instance
    '''
    
    if list_running == None or len(list_running) == 0:
        logging.warn("Removing all servers!")
    if path_new_file == None:
        path_new_file = path_conf_file
    
    regex_s_line = re.compile(s_line)
    
    in_file = open(path_conf_file, "r")
    conf = in_file.readlines()
    fh, abs_path = mkstemp()
    tmp = open(abs_path, "w")
    utils.fix_file_permissions(tmp)
    
    for line in conf:
        if len(line.strip()) == 0:
            pass
        match = regex_s_line.match(line)
        if match == None:
            tmp.write(line)                    
            
    in_file.close()    
        
    for i in list_running:
        s = '\tserver {0} {1}:{2} maxconn {3} check inter 1000 rise 2 fall 2 slowstart 1s\n'.format(i.instance_id, 
                i.ip_address, APACHE_PORT, MAX_CONN)
        tmp.write(s)
    
    # renaming temp file
    tmp.flush()
    tmp.close()
    # copies permission bits from the old file
    # see http://groups.google.com/group/comp.lang.python/browse_thread/thread/4c2bb14c12d31c29
    copystat(abs_path, path_new_file)
    # replace config. file and fix permission
    move(abs_path, path_new_file)
    #os.chmod(path_new_file, 0644)
    
    
def reload_haproxy(haproxy_config_file=None):
    '''
    Reload the configuration of HAPRoxy.
        * Root privileges are necessary to run this command
        :type haproxy_config_file: String
    '''
    logging.info('Reloading configuration')
    os_type = os.uname()[0]
    
    command = None
    try:
        with open(PID_FILE, 'r') as in_file:
            pid = in_file.readline()
            command = 'haproxy -f {1} -p {1} -sf {2}'.format(haproxy_config_file, PID_FILE, pid)
    except IOError:
            logging.warn("/var/run/haproxy.pid does not exist, trying to launch HAPROXY [MAC OS X?]")
            command = 'haproxy -f {0} -p {1}'.format(haproxy_config_file, PID_FILE)
    
    status = os.system(command)
    if status == 0: #OK
        logging.info("HAPRoxy configuration reloaded")
    else: # error
        logging.error("Unable to reload HAPRoxy configuration, status %d", status)
        


# Example 1
#reload_haproxy('/Users/michele/devel/haproxy-1.4.18/config_dec_14.cfg')

# Example 2
#if __name__ == '__main__':
    #update_haproxy_config("/Users/michele/devel/workspace/Ec2_Reserves/config_dec_14.cfg")
    #localhost = '127.0.0.1:200 a'
    #result = ip_regex.match(localhost)
    #if (result == None):
    #    print "Not found"
    #else:
    #    print result.string
