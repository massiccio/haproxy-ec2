'''
Created on Mar 13, 2012

@author: michele
'''
#from requests import get, ConnectionError, HTTPError
import human_curl as hurl

import argparse, time, csv, os, threading, random
import Queue
#from urllib2 import *

from commons import Response, Deviate, load_urls

import logging
from simple_pool import ThreadPool

log = logging.getLogger('client')
    
    

class Client():

    def __init__(self):
        self.completions = 0 # completions
        self.status = {} # dictionary used to store status codes and number
        #self.lock = threading.Lock() # lock for both completions and status code
        
        
        self.f = open('client.log', 'w', 16384)
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
            data = r.content #r.text
            
            row = []
            row.append('%d' % self.completions)
            row.append('%d' % r.status_code)
            row.append('%.4f' % response.rt)
            row.append('%d' % len(data)) #.encode('utf-8')))
            self.writer.writerow(row)
            
            self.q.task_done()
            
            # http://wiki.python.org/moin/PythonSpeed/PerformanceTips#String_Concatenation
            self.status[r.status_code] = get(r.status_code, 0) + 1
            
            #try:
            #    self.status[r.status_code] += 1
            #except KeyError:
            #    self.status[r.status_code] = 1
            
            #if self.status.has_key(r.status_code):
            #    old = self.status[r.status_code]
            #    self.status[r.status_code] = old + 1
            #else:
            #    self.status[r.status_code] = 1
                
                
            if self.completions % 500 == 0:
                print self.completions, r.status_code, len(data), response.rt
                
            del response
                
                

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
            
        
    
    def main(self, path, arr_rate, server='http://cloud-proxy.no-ip.org', port=80, scv=1.0):
        urls = load_urls(path)
        len_urls = len(urls)
        
        deviate = Deviate(arr_rate, scv)
        
        #max_val = len(urls) -1
        size = 1000000
        random.shuffle(urls) # [urls[random.randint(0, max_val)] for i in xrange(size)]
        random_sleep = [deviate.generateDeviate() for i in xrange(size)]
        
        print 'loaded %d urls, initialized random elements' % len(urls)
        print 'starting at %s' % time.asctime()
        
        pool = ThreadPool(100)
        log.info('Start test')
        #go = True
        start = time.time()
        counter = 0
        try:            
            add_task = pool.add_task
            counter_urls = 0
            counter_sleep = 0
            while self.go:
                tmp = time.time()
                url = urls[counter_urls]
                path = '%s%s' % (server, url)
                add_task(self.fetch_req, path)

                
                # hyper exponential distribution with cs2 4.8
                #if random.random() <= 0.75:
                #    arr_rate = 3.0
                #else:
                #    arr_rate = 50
                sleep_int = random_sleep[counter_sleep] #deviate.generateDeviate()
                delta = sleep_int - (time.time() - tmp)
                #if diff > 0.0:
                if delta > 0.0:
                    time.sleep(delta)
                #else:
                #time.sleep(sleep_int)
                    
                counter_sleep += 1
                counter_urls += 1
                counter += 1
                
                if counter_urls >= len_urls:
                    counter_urls = 0
                    random.shuffle(urls)
                
                if counter_sleep >= size -1:
                    counter = 0
                    log.info('Resetting counter')
                    
        except KeyboardInterrupt:
            self.go = False
            
            
            pool.wait_completion()
            self.t.join(1)
            stop = time.time()
            tmp = 0
            #status_copy = None
            #try:
            #    self.lock.acquire()
            tmp = self.completions
            status_copy = self.status
            #finally:
            #    self.lock.release()
            throughput = tmp  / (stop - start)
            arr_rate = counter / (stop - start)
            print '==================================\n'
            print '- Arrivals: %d' % counter
            print '- Arrival rate: %.3f jobs/sec' % arr_rate 
            print '- Throughput %.3f jobs/sec' % throughput
            print '- Status codes'
            for pair in status_copy.items():
                print '%d: %d' % (pair[0], pair[1])
            print '==================================\n'
            
            self.f.write('# Arrivals: %d\n' % counter)
            self.f.write('# Arrival rate: %.3f jobs/sec\n' % arr_rate) 
            self.f.write('# Throughput %.3f jobs/sec\n' % throughput)
            self.f.write('# Status codes\n')
            for pair in status_copy.items():
                self.f.write('#%d: %d\n' % (pair[0], pair[1]))
            
        finally:
            self.f.flush()
            os.fsync(self.f.fileno())
            self.f.close()
        
        
        

if __name__ == '__main__':
    
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.ERROR)
    
    
    parser = argparse.ArgumentParser(description='HTTP Client')
    parser.add_argument('-f', required=True, help='Path to the URLs')
    parser.add_argument('-l', type=float, required=False, default=1, help='Arrival rate')
    parser.add_argument('-s', default='http://cloud-proxy.no-ip.org', help='HAProxy IP')
    parser.add_argument('-p', type=int, default=80, help='Server port')
    parser.add_argument('-ca2', type=float, default=1.0, help='ca2')
    args = parser.parse_args()
    
    #print requests.defaults['keep_alive']
    #, 'pool_connections'=100, 'keep_alive'=True, 'max_retries'=3]
    Client().main(args.f, args.l, args.s, args.p, args.ca2)
