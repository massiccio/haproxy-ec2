'''
Created on Apr 3, 2012

@author: michele
'''

import random, math, logging



log = logging.getLogger('client')

class LogNormalRDG():
    '''
    Pseudo random generator that produces log norally distributed numbers
    '''
    def __init__(self, mean, scv):
        self.mean = mean
        self.scv = scv
        
        # variance
        sigma2 = math.log(scv + 1.0) # scv = e^(sigma2) - 1
        self.sigma = math.sqrt(sigma2)
        self.mu = math.log(mean) - (sigma2 / 2.0)
    
    def generateDeviate(self):
        return random.lognormvariate(self.mu, self.sigma)
    
    
    
class Deviate():
    
    def __init__(self, rate, scv=1.0):
        self.rate = rate
        self.scv = scv
        
        if scv > 1.0:
            print 'Using log-normal distribution'
            # the first argument is the mean value, not the rate!
            self.lognormal = LogNormalRDG(1.0  / rate, scv)
        
    def generateDeviate(self):
        if self.scv == 1.0:
            return random.expovariate(self.rate)
        else:
            return self.lognormal.generateDeviate()
         

def load_urls(path):
    '''
    Reads the file and creates a list with the URLs
        * param path: The path to the file
        * type path: string
        * rtype: list of strings
    '''
    
    log.info('Loading the list of the URLs')
    urls = []
    with open(path) as in_file:
        for tmp in in_file.readlines():
            urls.append(tmp)
    return urls

class Response():
    
    def __init__(self, rt, resp):
        self.rt = rt
        self.resp = resp


