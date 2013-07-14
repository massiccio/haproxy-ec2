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
Created on Apr 3, 2012

@author: michele
'''
import argparse, time, os, logging, random, csv, threading, Queue
#from urllib2 import *

import human_curl as hurl

from commons import load_urls, Deviate, Response
from simple_pool import ThreadPool

log = logging.getLogger('client')


SERVER='http://cloud-proxy.no-ip.org'
HOUR = 3600.0
SCV = 4.0 # squared coefficient of variation

def load_lambdas(path):
    log.info('Loading the lambdas')
    lines = []
    with open(path) as in_file:
        for tmp in in_file.readlines():
            if tmp.startswith('#'):
                continue
            y = [value for value in tmp.split()]
            lines.append(float(y[0]))
    return lines


class ClarknetClient():

    def __init__(self):
        self.arrivals = 0
        self.start = 0.0
        self.pool = ThreadPool(100)
        
        self.completions = 0 # completions
        self.status = {} # dictionary used to store status codes and number
        #self.lock = threading.Lock() # lock for both completions and status code
        
        
        self.f = open('trace.txt', 'w', 16384)
        self.f.write('# Client log, created on %s\n' % (time.ctime(time.time())))
        self.f.write('# Event, HTTP code, resp. time, bytes\n')
        self.writer = csv.writer(self.f, delimiter='\t', lineterminator='\n', quotechar='"')
        
        
        self.go = True
        
        # code used to write data to file and update the stats
        self.q = Queue.Queue(100000)
        self.t = threading.Thread(target=self.log)
        self.t.daemon = True
        self.t.start()
        
        
    def log(self):
        get = self.status.get
        
        while self.go:
            response = self.q.get()
            self.completions += 1
            
            r = response.resp
            data = r.text
            
            row = []
            row.append('%d' % self.completions)
            row.append('%d' % r.status_code)
            row.append('%.4f' % response.rt)
            row.append('%d' % len(data.encode('utf-8')))
            self.writer.writerow(row)
            
            self.q.task_done()
            
            # http://wiki.python.org/moin/PythonSpeed/PerformanceTips#String_Concatenation
            self.status[r.status_code] = get(r.status_code, 0) + 1                
                
            if self.completions % 500 == 0:
                print self.completions, r.status_code, len(data), response.rt
    
    
    def shutdown(self):
        if self.go == True:
            self.go = False
                
                
            self.pool.wait_completion()
            self.t.join(1)
            stop = time.time()
            tmp = 0
            tmp = self.completions
            status_copy = self.status
            throughput = tmp  / (stop - self.start)
            arr_rate = self.arrivals / (stop - self.start)
            print '==================================\n'
            print '- Arrivals: %d' % self.arrivals
            print '- Arrival rate: %.3f jobs/sec' % arr_rate 
            print '- Throughput %.3f jobs/sec' % throughput
            print '- Status codes'
            for pair in status_copy.items():
                print '%d: %d' % (pair[0], pair[1])
            print '==================================\n'
            
            # Write same stuff to file
            self.f.write('# Arrivals: %d\n' % self.arrivals)
            self.f.write('# Arrival rate: %.3f jobs/sec\n' % arr_rate) 
            self.f.write('# Throughput %.3f jobs/sec\n' % throughput)
            self.f.write('# Status codes\n')
            for pair in status_copy.items():
                self.f.write('#%d: %d\n' % (pair[0], pair[1])) 
        

    def main(self, path_urls, path_lambdas, haproxy=SERVER):
        if haproxy == SERVER:
            log.warning('Using public IP!')
        else:
            log.warning("Using HAProxy's private IP %s" % haproxy)
        
        urls = load_urls(path_urls)
        url_max_index = len(urls) -1 # max index array of URLs
        lambdas = load_lambdas(path_lambdas)
        
        # select only 24 hours, day 11, index 243:267
        lambdas = lambdas[243:277] # take 10 extra hours
        lambdas[:] = [x * 1.5 for x in lambdas] # scale up the load by 50%
        len_lambdas = len(lambdas)
        
        i = 0
        deviate = Deviate(lambdas[0], SCV)
        log.warning("Setting new lambda to %.3f" % lambdas[0])
        
        self.start = time.time()
        lambda_change_at = self.start + HOUR
        log.warning("Next reconfiguration in %d seconds" % HOUR)
        try:
            add_task = self.pool.add_task
            
            while i < len_lambdas and self.go:
                cur_time = time.time()
                if cur_time > lambda_change_at:                    
                    # change lambda
                    i += 1
                    if i == len_lambdas:
                        break
                    else:
                        deviate = Deviate(lambdas[i], SCV)
                        log.warning("Setting new lambda to %.3f" % lambdas[i])
                        lambda_change_at += HOUR
                        log.warning("Next reconfiguration in %d seconds" % HOUR)
                        
                # select random URL and delegate it to the thread pool
                self.arrivals += 1
                url = urls[random.randint(0, url_max_index)]
                path = '%s%s' % (haproxy, url)
                #log.info(path)
                add_task(self.fetch_req, path)
                
                # sleep
                sleep_time = deviate.generateDeviate()
                time.sleep(sleep_time)
                
            # shutdown, end of experiment    
            self.shutdown()
        except KeyboardInterrupt:
            # shutdown, interrupted experiment
            self.shutdown()            
        finally:
            self.f.flush()
            os.fsync(self.f.fileno())
            self.f.close()
            
            logging.shutdown()
            
            
            
    def fetch_req(self, url):
        start = time.time()
        try:
            r = hurl.get(url) #, verify=False, prefetch=True, timeout=20)
            stop = time.time()
            rt = stop - start
            self.q.put(Response(rt, r))
            
        
        except hurl.exceptions.HTTPError, e:
            log.error('The server couldn\'t fulfill the request.')
            log.error('Error code: %d' % e.code)
        except hurl.exceptions.CurlError, e:
            log.error('Network problem')
        #except ConnectionError, e:
        #    log.error('Network problem')
        #except HTTPError, e:
        #    print 'The server couldn\'t fulfill the request.'
        #    print 'Error code: ', e.code
 
        
        
        
if __name__ == '__main__':
    FORMAT = '%(asctime)s %(levelname)s %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.WARNING, filename='log.log')
    
    parser = argparse.ArgumentParser(description='HTTP Client')
    parser.add_argument('-f', required=True, help='Path to the URLs')
    parser.add_argument('-l', required=True, help='Path to load trace')
    parser.add_argument('-u', required=True, default=SERVER, help='URL of HAPRoxy (default public DNS name)')
    args = parser.parse_args()
    
    # see http://www.cloudiquity.com/2009/02/using-amazon-ec2-public-ip-address-inside-ec2-network/
    # There is a big hit in network latency between using internal and public IP address
    # If you communicate between instances using public or elastic IP address 
    # even in the same region you pay regional data transfer rates(0.01$ per GB in/out).
    
    ClarknetClient().main(args.f, args.l, args.u)
    
    
