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
Created on Feb 16, 2012

@author: michele
'''

import os, sys, logging, time, string, math, random
from boto.ec2 import EC2Connection
from pwd import getpwnam

'''
All running instances have the tag with key 'wikipedia':
    * The load balancer has value 'haproxy'
    * Apache servers have value 'apache'
'''
TAG_KEY = 'wikipedia'
TAG_VALUE_HAPROXY = 'haproxy'
TAG_VALUE_APACHE = 'apache'
        
ALWAYS_ON = 0
RESERVE = 1
        
class InstanceList():
    '''
    Class storing a dictionary with the running instances having a tag
    with key 'wikipedia' and value 'apache'. All other instances are ignored.
    The key is constituted by the instance ID, while
    the object is an object of type Instance.
    '''
    
    def __init__(self):
        '''
        The key of each element in the dictionary is constituted by the 
        instance ID, while the object is an object of type Instance
        '''
        self.running = dict()
        
        
    def add(self, instance):
        '''
        Adds the specified instance to this list
        :type instance: object of type Instance
        '''
        instance_id = instance.instance_id
        self.running[instance_id] = instance
        
    
    def is_present(self, instance):
        '''
        Checks whether the specified instance is in the list.
        :type instance: the instance to remove
        :rtype: Boolean
        :return: True if the instance is in the list, False otherwise
        '''
        #return instance.instance_id in self.running
        return self.is_present_key(instance.instance_id)
    
    
    def is_present_key(self, key):
        return key in self.running
        
    
    def get(self, instance_id):
        '''
        Gets the instance identified by the provided ID, if any
        :type instance_id: String
        :rtype: Instance, or None
        '''
        if instance_id in self.running:
            return self.running.get(instance_id)
        return None
     
     
    def remove_instance(self):
        '''
        Removes and returns a random instance. See dict.popitem()
        :type: The pair (key, value), 
        type <type 'tuple'>, 
        val (u'i-9bb943ff', <utils.utils.OnOffInstance instance at 0x10199f200>)
        val[0] will give the key, val[1] with give the value
        '''
        return self.running.popitem()
    
    
    def remove(self, instance_id):
        '''
        Removes the specifed instance from the running set
        :type instance_id: the instance ID 
        :rtype: Boolean 
        :return: True if the instance was removed, False otherwise
             (e.g., because the instance Id is not present).
        '''
        if instance_id in self.running:
            del self.running[instance_id]
            return True
        else:
            logging.warn("Remove failed, %s not in the running set", 
                        instance_id)
            return False
    
  
    def keys(self):
        '''
        Retuns a copy of the dictionary's list of keys. See dict.keys().
        :rtype: a list of strings
        '''
        return self.running.keys()



    def get_no_of_instances(self):
        '''
        Gets the number of instances in the list
        :rtype: int
        :return the number of instances
        '''
        return len(self.running)


    def values(self):
        return self.running.values()


    def get_running_servers(self):
        '''
        Gets a copy of the instances.
        :rtype: list
        :return: a copy of the instances
        '''
        return self.running.values()


    def dump(self):
        '''
        Logs all the instances in the list.
        :rtype: void
        '''
        for v in self.running.viewvalues():
            logging.info(v.__str__())

            
    def size(self):
        '''
        Returns the number of elements.
        '''
        return len(self.running)


class Instance():
    '''
    Stores the following data about an instance
    - instance ID
    - IP address
    - Launch time
    - state of the server (reserve or always on), ALWAYS_ON by default
    '''
    def __init__(self, instance, state=ALWAYS_ON): #instance_id, ip_address, launch_time):
        '''
        Instance Id, e.g., i-45b13e20, and private IP, 
        e.g., ec2-23-20-7-178.compute-1.amazonaws.com, and launch time
        
        :type instance boto.ec2.Instance 
        :param instance An EC2 instance
        '''
        self.instance_id = instance.id #instance_id
        self.ip_address = instance.ip_address #ip_address
        self.launch_time = extract_launch_time(instance.launch_time) #launch_time
        self.state = state
        
        
    def __str__(self):
        return '[instance id: %s, IP: %s, launched at: %s]' % (self.instance_id, self.ip_address, time.asctime(self.launch_time))
    
    
    
    def __key(self):
        return (self.instance_id)
        
        
    def __hash__(self):
        return hash(self.__key())
    
    
    def __eq__(self, other):
        if not isinstance(other, Instance):
            return False
        if self.instance_id != other.instance_id:
            return False


class OnOffInstance(Instance):
    
    '''
    Stores the following data about an instance
    - instance ID
    - IP address
    - Launch time
    Also, it stores the state (e.g., whether this instance is active or not)
    '''
    def __init__(self, instance, active=True):
        '''
        Instance Id, e.g., i-45b13e20, and private IP, 
        e.g., ec2-23-20-7-178.compute-1.amazonaws.com, and launch time
        
        :type instance boto.ec2.Instance 
        :param instance An EC2 instance
        :type active: Boolean
        :param active: flat used to indicated whether an instance is active or not
        '''
        Instance.__init__(self, instance)
        self.active = active



def create_ec2_connection():
    '''
    Creates a connection to Amazon EC2
        :rtype: boto.ec2.EC2Connection
    '''
    aws_access_key_id = 'xxxxxxxx'
    aws_secret_access_key = 'yyyyyyyyy'
    conn = EC2Connection(aws_access_key_id, aws_secret_access_key)
    return conn


def create_filter(key=TAG_KEY, value=TAG_VALUE_APACHE):
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



def extract_launch_time(launch_time):
    '''
    The input is something like this
    2012-02-09T09:13:55.000Z
    This function returns a time.struct_time object, see
    http://docs.python.org/library/time.html#time.strptime
    
    :type launch_time: String
    :rtype: time.struct_time 
    '''
    return time.strptime(launch_time[:19], "%Y-%m-%dT%H:%M:%S")



def fix_file_permissions(f):
    '''
    Changes the file permission to the real user as 0644 (using login username)
    '''
    pw = None
    try:
        pw = getpwnam(os.getlogin())
    except Exception:
        pw = getpwnam('ubuntu')
        
    os.chown(os.path.realpath(f.name), pw.pw_uid, pw.pw_gid)
    os.chmod(os.path.realpath(f.name), 0644)


def check_if_sudo():
    '''
    Checks if the process is running as root/sudo, and if not, it asks
    for the password
    '''
    
    # http://stackoverflow.com/questions/5222333/authentication-in-python-script-to-run-as-root
    euid = os.geteuid()
    if euid != 0: # root
        logging.warn("Script not started as root. Running sudo..")
        print '##################################################'
        print '### Script not started as root. Running sudo.. ###'
        print '##################################################'
        args = ['sudo', sys.executable] + sys.argv + [os.environ]
        # the next line replaces the currently-running process with the sudo
        os.execlpe('sudo', *args)


    
def exp_deviate(mean):
    '''
    Generates an exponentially distributed variate with the specified mean
    rtype: float
    '''
    return -mean * math.log(1.0 - random.random())
    