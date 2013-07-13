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
Created on Mar 8, 2012

@author: michele

Script used to parse the logs of HAProxy
'''
import string, re
from numpy import average, array, var, min, max

import sys

def main(path):
    pattern = re.compile('\s*')    
    #path = 'haproxy_Mar_13.log'

    serv_times = []
    resp_times = []
    errors = {}
    
    with open(path, 'r') as f:
        for line in f.readlines():
            split = re.split(pattern, line)
            if len(split) != 21:
                continue
            
            #print split
            if split[18] == '/admin?stats':
                continue # ignore stats
            
            # the 10 element is the one including the response time,
            # see http://code.google.com/p/haproxy-docs/wiki/HTTPLogFormat
            # before that, tehre are 3 fields indicating the date and 1
            # indicating the IP address of HAProxy
            
            stats = string.split(split[9], '/')
            if int(stats[3]) > 0:
                serv_times.append(int(stats[3])) # service time
                resp_times.append(int(stats[4])) # resp. time
                
            if split[10] in errors:
                val = errors[split[10]]
                errors[split[10]] = val+1
            else:
                errors[split[10]] = 1
                
    print 'population %d' % len(serv_times)
    for a in errors.iteritems():
        print a[0], a[1]
    
    ar = array(serv_times)
    mean = average(ar)
    variance = var(ar)
    
    print '# ==================='
    print '# Service times'
    print '# ==================='
    print 'mean %.3f ms' % mean
    print 'var %.3f' % variance
    print 'cs2 %.3f' % (variance / (mean*mean))
    print 'min %d, max %d' % (min(ar), max(ar))
    
    
    ar = array(resp_times)
    mean = average(ar)
    variance = var(ar)
    print '# ==================='
    print '# Response times'
    print '# ==================='
    print 'mean %.3f ms' % mean
    print 'var %.3f' % variance
    print 'cs2 %.3f' % (variance / (mean*mean))
    print 'min %d, max %d' % (min(ar), max(ar))

        
if __name__ == '__main__':
    if len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        print "Usage 'python log_analyzer.py <path_to_haproxy_log>'"
        sys.exit(1)
    #a = array([1,2,3,4,5, 1])
    #print average(a)
