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
Created on Dec 19, 2011

@author: michele
'''

from math import sqrt, isinf
import numpy
import commons

class AnnOperRes():
    '''
    Annal Operation Research paper: evaluates the cost function for a particular
    configuration
    '''


    def __init__(self, N, nu, c1, c2):
        self.N = N
        self.nu = nu
        self.costs = commons.Costs(c1, c2)
        
    
	def zeros(self, size):
        '''
        Creates an array with the specified size
        '''
        return numpy.zeros(size, dtype=numpy.float64)
     
        
    def cost(self, res, load):
        '''
        Computes the cost, given the given no. of reserves (and parameters)
        and load
            :type res: commons.Reserves
            * res: res parameters
            :type load: commons.Load
            * load: arrival rate and service rates
            * rtype: commons.Solution
        '''
        U = res.U
        D = res.D
        m = res.m
        lam = load.lam
        mu = load.mu
        N = self.N
        nu = self.nu
        
        if res.m == 0:
            return self.cost0(load)
        if res.D == res.U:
            return self.cost1(m, U, load)
        
       
        
        p = 1.0 # eventually will hold p0s
        rho = load.get_load()
        n = self.N - m
        p0 = 1.0 # prob res off
        L = 0.0 # average number of jobs
        
        
        if self.N == rho:
            raise ArithmeticError("N should be larger than the load!")

        # line 18
        for j in xrange(1, res.D+1):
            p = p * rho / min(j, n)
            p0 = p0 + p # update sum
            L = L + j * p # update average

        b = lam + n * load.mu + nu;
        # root < 1
        z1 = (b - sqrt(b * b - 4 * n * lam * mu)) / (2 * lam);
        # root > 1
        z2 = (b + sqrt(b * b - 4 * n * lam * mu)) / (2 * lam);
        h1 = 1 / (z2 - 1) # constant
        
        h2 = 1 / (N * mu - lam) # constant
        m1 = 1 / mu # constant
        if isinf(h2):
            raise ArithmeticError("h2 is infinity!")
        
        #line 29
        #array of consts for p0j, j=s+1,...,K
        r = self.zeros(U - D)
        r[0] = 1 + mu * min(U, n) / lam
        
        for j in xrange(1, res.U - res.D):   #compute r(j)
            try:
                r[j] = 1 + r[j - 1] * mu * min(U + 1 - (j + 1), n) / lam
            except FloatingPointError, e:
                #print "balbla {0}".format(e)
                print r[j-1], mu,  min(U + 1 - (j + 1), n), lam
                print 'm %d, D %d U %d' % (m, D, U)
                raise (e)
            
        p0U = p / r[U - D - 1] # p0U
        p0 = p0 + p0U # update p0
        L = L + U * p0U # update L
        
        #line 37
        # compute p0j backwards, j=U-1,...,D+1
        for j in xrange(0, (U - D - 1)):
            p = r[j] * p0U
            p0 = p0 + p # update p0
            L = L + (U - (j + 1)) * p # // update L

        # line 42
        norm = p0 # normalization constant; sum of all probs
        p1j = self.zeros(U - D) # p1j for j=D+1,...,U
        bj = self.zeros(U - D) # bj=lam+mj+nu
        for j in xrange(0, U - D):
            bj[j] = lam + nu + min(D + (j + 1), n) * mu
        
        a = 0.0
        aj = self.zeros(U - D - 1) # aj computed recurrently
        if (res.D < res.U - 1):            # line 48
            aj[0] = min(D + 2, n) * mu / bj[0] # aD+1
            for j in xrange(1, U - D - 1): #aj for j=D+2,...,U-1
                aj[j] = min(D + (j + 1) + 1, n) * mu / (bj[j] - lam * aj[j - 1])
                
            a = aj[U - D - 2] # used to compute p1U
        else:
            a = 0.0   # does not appear in p1U
            
        # line 58, compute p1U
        p1j[U - D - 1] = p0U * lam * z1 / (bj[U - D - 1] - lam * a - lam * z1);
        norm = norm + p1j[U - D - 1] # update norm
        L = L + U * p1j[U - D - 1]; # update L
        
        # line 61, compute p1j backwards from p1U-1
        for j in xrange(U - D - 2, -1, -1):
            p1j[j] = aj[j] * p1j[j + 1]
            norm = norm + p1j[j] # update norm
            L = L + (D + (j + 1)) * p1j[j] # update L
        # backwards partial sums p1j for j=D+1,...,U
        p1 = self.zeros(U - D);
        p1[U - D - 1] = p1j[U - D - 1] # last element

        for j in xrange(U - D - 2, -1, -1): # other partial sums
            p1[j] = p1[j + 1] + p1j[j]
            
        # line 71
        g1 = (p0U + p1j[U - D - 1]) * h1 # g1(1)=sum p1j for j=U+1,...
        g1p = g1 * (U + 1 + h1) # g1^prime(1)
        p2 = (p1[0] + g1) * self.nu * m1 / min(D + 1, self.N) # p2D+1
        norm = norm + p2 # update norm
        L = L + (D + 1) * p2 # update L
        
        for j in xrange(D+2, U+1, 1): # compute p2j for j=D+2,...,U
            p2 = ((p1[j - D - 1] + g1) * self.nu + p2 * lam) * m1 / min(j, self.N) # p2j
            norm = norm + p2 # update norm
            L = L + j * p2 # update L
            
        g2 = 0.0
        g2p = 0.0
        if U + 1 < self.N: # Case 2
            zj = 1.0 # z2^-j
            for j in xrange(U+1, self.N): #compute p2j for j=U+1,...,N-1
                p2 = (g1 * self.nu * zj + p2 * lam) * m1 / j # p2j
                norm = norm + p2 # update norm
                L = L + j * p2 # update L
                if j < self.N - 1:
                    zj = zj / z2 # update zj
            g2 = (lam * p2 + nu * g1 * zj * h1) * h2
            g2p = (lam * (g2 + N * p2) + nu * g1 * zj * h1 * (N + h1)) * h2
        else: # case 1: U+1 >= N
            g2 = (lam * p2 + nu * g1 * z2 * h1) * h2
            g2p = (lam * (g2 + (U + 1) * p2) + nu * g1 * z2 * h1 * (U + 1 + h1)) * h2

        # line 97
        norm = norm + g1 + g2 # UPDATE NORMALIZATION CONSTANT
        L = L + g1p + g2p # update mean

        try:
            p0 = p0 / norm # normalize p0
        except FloatingPointError, e:
            print p0, norm, res.m, res.D, res.U
            raise e
        L = L / norm # normalize mean
        c = L * self.costs.c1 + (N - m * p0) * self.costs.c2 # average cost
        return commons.Solution(c, res)
    

    def cost0(self, load):
        '''
        Cost of M/M/N queue; (N servers);
        arr rate lam, ser rate mu;
        holding cost c1, server cost c2;
        '''
        p = 1.0 # eventually it will hold pN
        rho = load.get_load()
        s = 1.0 # sum of probabilities 0...N
        L = 0.0   # avg. no. of jobs )...N
        for j in xrange(1, self.N + 1):
            p = p * rho / j
            s = s + p # update sum
            L = L + j * p # update average
        h1 = rho / (self.N - rho) # constant
        g1 = p * h1
        norm = s + g1 # normalization constant
        g1 = g1 / norm # normalize g1
        L = L / norm; # normalize mean
        L = L + g1 * (self.N + 1 + h1) # average no. of jobs present
        c = L * self.costs.c1 + self.N * self.costs.c2 # average cost
        return commons.Solution(c)
        
        
    def cost1(self, m, K, load):
        '''
        Total number of servers N, res m, threshold K;
        arr rate lam, ser rate mu, switch-on rate nu;
        holding cost c1, server cost c2; assume N-m-1 <= K
        '''
        p = 1.0  # eventually will hold p0K
        rho = load.get_load()
        norm = 1.0 # normalization constant: sum of all probs
        L = 0.0 # avg. no. of jobs 0...K
        for j in xrange(1, K + 1):
            if j < self.N - m:
                p = p * rho / j
            else:
                p = p * rho / (self.N - m)
            norm = norm + p # update sum
            L = L + j * p # update average
            
        b = load.lam + (self.N - m) * load.mu + self.nu
        # root > 1
        z2 = 0.0
        try:
            z2 = (b + sqrt(b * b - 4 * (self.N - m) * load.lam * load.mu)) / (2 * load.lam)
        except ZeroDivisionError, e:
            print load.lam
            raise e
            
        zj = 1 # constant (will contain z2^-j)
        h1 = 1 / (z2 - 1) # constant
        h2 = 1 / (self.N * load.mu - load.lam) # constant
        m1 = 1 / load.mu # constant
        g1 = p * h1 # g1(1)=P(res being switched on)
        g1p = g1 * (K + 1 + h1) # g1^prime(1)
        
        g2 = 0.0
        g2p = 0.0
        # line 26
        if K + 1 >= self.N: # case 1
            g2 = g1 * self.nu * z2 * h1 * h2; # g2(1)
            g2p = h2 * (load.lam * g2 + self.nu * z2 * h1 * g1p); # update average
        else:
            p2 = self.nu * g1 * m1 / (K + 1) # p2K+1;
            g2 = p2  # sum of all p2j
            L = L + (K + 1) * p2 # update mean
            for j in xrange(2, self.N - K):
                # compute p2j sum and mean j=K+2,...,N-1
                zj = zj / z2 # update z2^-j
                p2 = (load.lam * p2 + self.nu * zj * g1) * m1 / (K + j) # next p2j
                g2 = g2 + p2 # update sum
                L = L + (K + j) * p2 # update mean
            g22 = h2 * (load.lam * p2 + self.nu * g1 * zj * h1) # g2(1)
            g2 = g2 + g22 # update sum of p2j
            g2p = h2 * (load.lam * g22 + self.N * load.lam * p2 + self.nu * zj * h1
                        * ((self.N - K - 1) * g1 + g1p))
            
        # line 43
        norm = norm + g1 + g2 # update normalization constant
        L = L + g1p + g2p # update mean
        g1 = g1 / norm # normalize g1
        g2 = g2 / norm # normalize g2
        L = L / norm # normalize mean
        c = L * self.costs.c1 + (self.N - m * (1 - g1 - g2)) * self.costs.c2 # average cost
        return commons.Solution(c, commons.Reserves(m, K, K))

        
       

