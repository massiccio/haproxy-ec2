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
Created on Mar 6, 2012

@author: michele

Script used to start apache, mysql and memcached and configure them

The following variables should be set:
- UBUNTU_11_10_AMI
- CLIENT_AMI Client running the load generator
- PLACEMENT In which region should the instances be placed?
- HAPROXY_AMI AMI running HAproxy
- AMI AMI containing Memcached, MySQL and Apache
- KEY_PATH path to the .pem file
- EC2 credentials

By default all instances are c1.medium. This behavior can be changed by setting a different value in C1_MEDIUM_INSTANCE
'''

import time, logging, os, string, argparse, pwd
from boto.ec2 import EC2Connection
from tempfile import mkstemp
from monitor.commons import create_ec2_connection

# ------------------------------------------------------------------------- #
#                               GLOBALS                                     #
# ------------------------------------------------------------------------- #

KEY = 'wikipedia'
MYSQL = 'mysql'
MEMCACHED = 'memcached'
APACHE = 'apache'
HAPROXY = 'haproxy'
CLIENT = 'client'



# Default AMI ubuntu, http://alestic.com/
UBUNTU_11_10_AMI = 'ami-baba68d3' # replace with your own

CLIENT_AMI = 'ami-xxxxx' # OpenJDK 7

PLACEMENT='us-east-1b'

HAPROXY_AMI = 'ami-yyyyyy'

AMI = 'ami-zzzzz'
C1_MEDIUM_INSTANCE= 'c1.medium'
KEY_PATH = 'path to .pem file'

# Amazon EC2 credentials
aws_access_key_id = 'your key id here'
aws_secret_access_key = 'your key here'


def create_filter(key=KEY, value=APACHE):
    '''
    Creates a filter to get the instances with tag 'wikipedia:apache'
    which are in running state. By default, the instance with tag 'wikipedia:apache'
    are returned, but the default behavior can be changed by means of the
    parameters
    
        * type key: string
        * param key: the key of the tag
        * type value: string
        * param value: the value of the tag
    '''
    tmp = string.join(['tag:', key], sep='')
    tag_filter = {tmp:value} # the ':' should not have spaces around
    tag_filter['instance-state-name'] = 'running'
    return tag_filter


def get_instances(conn, tag):
    f = create_filter(key=KEY, value=tag)
    reservations = conn.get_all_instances(filters=f)
    instances = [i for r in reservations for i in r.instances]
    
    logging.info("Tag %s" % tag)
    for i in instances:
        logging.info("id %s, public ip %s" % (i.id, i.ip_address))
        
    return instances

def recovery():
    '''
    Starts the services on running instances
    '''
    conn = create_ec2_connection(aws_access_key_id, aws_secret_access_key)

    apaches = get_instances(conn, APACHE)
    memcached = get_instances(conn, MEMCACHED)
    mysql = get_instances(conn, MYSQL)
    client = get_instances(conn, CLIENT)
    
    memcached = memcached[0]
    mysql = mysql[0]
    
    start_services(mysql, memcached, apaches)


def setup_client(client):
	'''
	Sets up the client: upload some code from this host, download a python library from github and install it.
	'''
    ip_address = client.ip_address
    destination = 'ubuntu@%s:~/' % ip_address
    abs_path = 'client/client_req.py client/simple_pool.py client/high.load client/clarknet.py client/commons.py ../traces/trace_clarknet_scaled.txt'
    status = os.system('scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s %s' % (KEY_PATH, abs_path, destination))
    if status == 0:
        logging.info('Copied load generator at %s' % ip_address)
    else:
        logging.error('Unable to copy load generator at %s' % ip_address)
        
    # http://stackoverflow.com/questions/5746325/how-do-i-download-a-tarball-from-github-using-curl    
    cmd = 'curl -L https://github.com/kennethreitz/requests/tarball/master | tar zx; curl -L https://github.com/Lispython/human_curl/tarball/master | tar xz; wget http://pypi.python.org/packages/source/s/setuptools/setuptools-0.6c11.tar.gz'
    address = 'ubuntu@%s' % ip_address
    status = os.system("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s '%s'" % (KEY_PATH, address, cmd))
    if status == 0:
        logging.info('Downloaded requests python module at %s' % ip_address)
    else:
        logging.error('Unable to download python module at %s' % ip_address)


def wait_for_running_state(instances, timeout=300):
    '''
    Waits for the instances specified to go in running state
        * param instances: list of instances
        * type instances: list of boto.ec2.instance.Instance object
        * param timeout: max no. of seconds to wait
        * type timeout: int
        * type: void
    '''
    start_time = time.time()
    to_go = len(instances)
    while time.time() - start_time < timeout and to_go > 0:
        to_go = len(instances)
        for i in instances:
            i.update()
            if i.update() == 'running' and i.ip_address != None and i.private_ip_address != None:
                #logging.info('instance %s now running at %s', i.id, i.ip_address)
                to_go -= 1
            else:
                logging.debug('instance %s is in state %s', i.id, i.state)
        
        if to_go > 0:    
            logging.info('[%.1f/%d]' % ((time.time() - start_time), timeout))
            time.sleep(3)
            
                
    if to_go > 0:
        msg = "Timeout expired, missing %d instances" % to_go
        logging.error(msg)
        raise UserWarning(msg)
    
    
    for i in instances:
        logging.info('instance %s now running at %s, private IP %s', i.id, i.ip_address, i.private_ip_address)
    

def start_services(mysql, memcached, apaches, key_path=KEY_PATH):
	'''
	Start MySQL, memcached and Apache services on remote machines.
	'''
    
    if mysql.ip_address == None:
        raise RuntimeError("Null address for MySQL!!")
    if memcached.ip_address == None:
        raise RuntimeError("Null address for Memcached!!")
    
    cmd = 'sudo service mysql start'
    address = 'ubuntu@%s' % mysql.ip_address
    status = os.system("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s '%s'" % (key_path, address, cmd))
    if status == 0:
        logging.info('Started mysql')
    else:
        logging.error('Unable to start mysql at %s' % address)
    
    # start memcached
    address = 'ubuntu@%s' % memcached.ip_address
    cmd = 'sudo memcached -u nobody -d -p 11211 -m 1280 -c 4096 -R 40'
    status = os.system("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s '%s'" % (key_path, address, cmd))
    if status == 0:
        logging.info('Started memcached')
    else:
        logging.error('Unable to start memcached at %s' % address)
    
    
    memcached_private_ip = memcached.private_ip_address
    mysql_private_ip = mysql.private_ip_address
        
    if memcached_private_ip == None or mysql_private_ip == None:
        raise RuntimeError('private IPs: mysql %s, memcached %s' %
                           (memcached_private_ip, mysql_private_ip)) 
    
    fh, abs_path = mkstemp()
    tmp = open(abs_path, "w")
    tmp.write('<?php\n')
    tmp.write('$wgDBserver = "%s";    // MySQL server IP (using port 3306)\n' % mysql_private_ip)
    tmp.write('$wgMemCachedServers = array (\n')
    tmp.write("\t0 => '%s:11211',        // memcached servers \n" % memcached_private_ip)
    tmp.write(');\n')
    tmp.write('?>')
    tmp.flush()
    tmp.close()
    
    cmd = 'sudo service apache2 start'
    for i in apaches:
        i.update()
        destination = 'ubuntu@%s:/var/www/mediawiki/IPSettings.php' % i.ip_address
        #p = subprocess.Popen(['scp', abs_path, destination])
        status = os.system('scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s %s' % (key_path, abs_path, destination))
        #sts = os.waitpid(p.pid, 0)
        if status != 0:
            logging.error('Unable to copy config file at %s' % address)
        
        # start apache
        address = 'ubuntu@%s' % i.ip_address
        status = os.system("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s '%s'" % (key_path, address, cmd))
        if status == 0:
            logging.info('Started apache at %s' % i.ip_address)
        else:
            logging.error('Unable to start apache at %s' % i.ip_address)


def main(apache_servers, key_path=KEY_PATH):
    '''
    Launches the instances
        * param apache_servers: the number of apache servers to launch
        * type apache_servers: int
        * param key_path: the path to the SSH key
        * type key_path: string
    '''
    conn = create_ec2_connection(aws_access_key_id, aws_secret_access_key)
    
    
    res = conn.run_instances(HAPROXY_AMI, 1, 1, key_name='haproxy-key', 
                             security_groups=['default'], instance_type='m1.small', 
                             placement=PLACEMENT)
    res.instances[0].add_tag(KEY, HAPROXY)

    # mysql and memcached
    res = conn.run_instances(AMI, min_count=2,
            max_count=2, key_name='haproxy-key',
            instance_type=C1_MEDIUM_INSTANCE, placement=PLACEMENT, security_groups=['default'])
    instances = res.instances # list
    
    mysql = instances[0]
    memcached = instances[1]
    
    mysql.add_tag(KEY, MYSQL)
    memcached.add_tag(KEY, MEMCACHED)
    
    
    # client
    res = conn.run_instances(CLIENT_AMI, 1, 1, key_name='haproxy-key', 
                             security_groups=['default'], 
                             instance_type=C1_MEDIUM_INSTANCE, 
                             placement=PLACEMENT)
    client = res.instances[0]
    
    client.add_tag(KEY, CLIENT)
    
    # apache servers
    res = conn.run_instances(AMI, min_count=apache_servers,
            max_count=apache_servers, key_name='haproxy-key',
            instance_type=C1_MEDIUM_INSTANCE, placement=PLACEMENT, security_groups=['default'])
    apaches = res.instances # list
    
    for i in apaches:
        i.add_tag(KEY, APACHE)
        
    total = instances + apaches
    total.append(client)
    wait_for_running_state(total)
    
    logging.info('All instances in running state, waiting for the initialization to complete')
    
    time.sleep(15)

    recovery()
        
        
    

if __name__ == '__main__':
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.INFO)
    if os.path.exists(KEY_PATH) == True:
        logging.info("Key path valid")
    else:
        raise ValueError("Key path invalid")
    
    parser = argparse.ArgumentParser(description='HAProxy monitor')
    parser.add_argument('-n', type=int, required=False, default=1, help='Number of apache servers')
    parser.add_argument('-key', required=False, default='~/.ssh/haproxy-key.pem', help='path to the SSH key')
    parser.add_argument('-r', required=False, default=False, help='Recover (True) or launch new instances (False). Default False')
    args = parser.parse_args()
    
    if args.r:
        logging.info("Recovering the servers")
        recovery()
    else:
        logging.info('Launching %d apache servers' % args.n)
        main(args.n, args.key)
    