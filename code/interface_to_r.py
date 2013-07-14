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
Created on Apr 5, 2012

Invokes an R script via shell and waits for the process to complete.

@author: Michele Mazzucco
'''

import subprocess, os, time, signal, sys
import logging as log

global GO

def r_prediction(in_file, out_file, pid):
    proc = subprocess.Popen(['./forecast.sh', in_file, out_file], 
                            close_fds=True, shell=False, cwd='../scripts')

    
    while proc.poll() is None:
            log.debug("still working")
            time.sleep(1)
        
    os.kill(pid, signal.SIGUSR1)
    
    

def completed_handler(signum, stack):
    print "Completed"
    global GO
    GO = False


if __name__ == '__main__':
    counter = 0
    path = '/tmp/available_trace.tmp'
    with open('../traces/trace_clarknet_scaled.txt') as f:
        with open(path, 'w') as tmp:
        
            for line in f.readlines():
                if line.startswith('#'):
                    continue

                tmp.write(line)
                counter += 1
                if counter == 243:
                    break
                
                
    main_pid = os.getpid()
    pid = os.fork()
    signal.signal(signal.SIGUSR1, completed_handler)
    global GO
    GO = True

    if pid: # parent
        while GO == True:
            time.sleep(1)

        os.remove(path)
    else: # child
        r_prediction(path, 'result.txt', os.getpid())
        
        
        