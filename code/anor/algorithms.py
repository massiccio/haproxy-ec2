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
Created on Feb 21, 2012

Algorithms used to find the optimal/heuristic solution to the queueing model for a set of input parameters.

@author: michele
'''

import commons, anor
import random
from math import exp, sqrt, ceil, floor
import decimal

from commons import Reserves


class Heuristic:
    '''
    Heuristic policy based on a M/M/1 approximation.
    '''


    def __init__(self, N, nu, c1, c2, cores=1):
        '''
        Constructor
            * N: total number of servers
            * nu: rate required to power on servers (i.e., servers require,
              on average 1/nu time units to be switched on)
            * c1: holding cost
            * c2: cost for servers
            * cores: number of cores per server 
        '''
        self.N = N
        self.nu = nu
        self.costs = commons.Costs(c1, c2)
        self.cores = cores
        
        
    def computeN(self, load):
        '''
        Computes the number of servers to run. Implements equation 45.
        '''
        rho = load.get_load()
        return int(floor(rho + 0.5 * (1.0 + sqrt(1.0 + 4.0 * rho * (self.costs.c1 / self.costs.c2)))))
    
    
    def computeL(self, load, n):
        '''
        Computes the average number of jobs in the system.
        This method uses the M/M/1 expression for estimating L, see Equation 44.
        '''
        rho = load.get_load()
        return (rho / (n - rho))
        
        
    def computeU(self, load, n):
        '''
        Computes the lower threshold, D (the threshold used to power down
        servers). Equation 47.
        '''
        u1 = (n * load.mu - load.lam) / self.nu
        u2 = (self.N * load.mu - load.lam) / self.nu
        u3 = self.costs.c2 * (n * load.mu - load.lam) / (self.costs.c1 * load.mu)

        tmp1 = n - 1
        tmp2 = int(ceil(u1 + u3 * (1.0 + sqrt(1.0 + 2.0 * u2 / u3))))
        return max(tmp1, tmp2);
    
    
    def solve(self, res, load):
        '''
        Produces a solution for the given number of reserves and load
            * type res: anor.commons.Reserves
            * type load: anor.commons.Load
            * rtype: anor.commons.Solution
        '''
        return anor.AnnOperRes(self.N, self.nu, self.costs.c1, self.costs.c2).cost(res, load)
    
    
    def compute_queue_thresholds(self, load, m):
        D = self.N - m - 1
        #n = self.N - m
        U = self.N #self.computeU(load, n) #self.N # simpler heuristic #self.computeU(load, n)
        return D, U
    
    
    def heuristic(self, load):
        '''
        Heuristic policy
            * load: The load (in erlangs)
            * returns: An object of type anor.commons.Solution
        '''
        n = self.computeN(load) # eq 45, number of servers always on
        m = max(0, self.N - n) # eq 46, nunber of reserves
        diff = m % self.cores
        
        sol = None
        if diff == 0:
            n = self.N - m
            D, U = self.compute_queue_thresholds(load, m)
            
            res = commons.Reserves(m, D, U)
            sol = self.solve(res, load)
        else:
            n1 = n + diff
            n2 = n - diff
            
            res1 = None
            res2 = None
            c1 = None
            c2 = None
            
            if n2 > 0:
                m = max(0, self.N - n2)
                n2 = self.N - m
                D, U = self.compute_queue_thresholds(load, m)
            
                res1 = commons.Reserves(m, D, U)
                c2 = self.solve(res1, load)
                
            if n1 < self.N:
                m = max(0, self.N - n1)
                n1 = self.N - m
                D, U = self.compute_queue_thresholds(load, m)
            
                res2 = commons.Reserves(m, D, U)
                c1 = self.solve(res2, load)
                
            if c1 == None and c2 == None:
                raise RuntimeError('Unable to find solution!')
            
            if res1 == None:
                sol = self.solve(res2, load)
            elif res2 == None:
                sol = self.solve(res1, load)
            else:
                c1 = self.solve(res1, load)
                c2 = self.solve(res2, load)
                if c1.__cmp__(c2) < 0:
                    sol = c1
                else:
                    sol = c2
        
        if sol == None:
            raise RuntimeError("Null result")            
        return sol
    
        
    def heuristic_m_fixed(self, load):
        '''
        Heuristic policy, to be used when the number of reserves is fixed
            * load: The load (in erlangs)
            * returns: An object of type anor.commons.Solution
        '''
        D = self.N - self.m - 1
        n = self.N - self.m
        U = self.computeU(load, n)
        
        res = commons.Reserves(self.m, D, U)
        return self.solve(res, load)


class Exhaustive():
    '''
    Optimal policy - exhaustive search.
    '''


    def __init__(self, N, nu, c1, c2):
        '''
        Constructor
            * N: total number of servers
            * nu: rate required to power on servers (i.e., servers require,
              on average 1/nu time units to be switched on)
            * c1: holding cost
            * c2: cost for servers
        '''
        self.N = N
        self.nu = nu
        self.costs = commons.Costs(c1, c2)
    
    
    def cost(self, res, load):
        '''
        Returns an object of type Solution
        '''
        return anor.AnnOperRes(self.N, self.nu, self.costs.c1, self.costs.c2).cost(res, load)
    
    def exhaustive_search(self, load):
        rho = load.get_load()
        min_u = int(floor(rho))
        best = self.cost(commons.Reserves(0, 0, 0), load)
        for m in xrange(0, self.N):
            n = self.N - m
            for u in xrange(min_u, 80):
                for d in xrange(0, u):
                    # see comment at the beginning of cost1.m
                    if d == u and u < n - 1:
                        continue
                    res = commons.Reserves(m, d, u)
                    tmp = self.cost(res, load)
                    # print tmp.__str__()
                    if tmp.__cmp__(best) < 0:
                        best = tmp
        return best
        
        
        

class SimulatedAnnealing():
    '''
    Simulated Annealing
    '''


    def __init__(self, N, nu, c1, c2, cores=1):
        '''
        Constructor
            * N: total number of servers
            * nu: rate required to power on servers (i.e., servers require,
              on average 1/nu time units to be switched on)
            * c1: holding cost
            * c2: cost for servers
            * cores: (default 1) increment/decrement of m 
        '''
        self.N = N
        self.nu = nu
        self.cost = commons.Costs(c1, c2)
        self.time = 0
        self.cores = cores
        
        
    def __str__(self):
        return 'N %d, nu = %.3f, c1 = %.2f, c2 = %.2f, cores %d' % (self.N, self.nu, self.cost.c1, self.cost.c2, self.cores)
        
    def get_iterations(self):
        '''
        Gets the number of iterations made by the algorithm
        '''
        return self.time
        
    
    def __def_solution(self, load):
        '''
        Creates the default solution.
        It is not possible to use the ANOR heuristic here because it tends
        to use very large upper thresholds, which might cause overflow.
        '''
        n = int(round(load.get_load() + 0.5))
        if n % self.cores != 0:
            n += n % self.cores
        if n > self.N:
            n -= self.cores
            
        U = self.N
        D = n - 1
        return Reserves(self.N - n, D, U).create_solution(self.N, self.nu, self.cost, load)
    
    
    def create_neighbor(self, cur_state, load):
        '''
        Creates a neighbor solution of the current state
            * cur_state: Solution
            * load: Load
            * Return: an object of type Solution by varying m, D, and U
        '''
        m = cur_state.get_m()
        d = cur_state.get_d()
        u = cur_state.get_u()
        max_u = self.N * 3
        tmp = []
        
        if m > self.cores and u >= (self.N - (m - self.cores) - 1):
            tmp.append(Reserves(m - self.cores, d, u))
        
        if m < self.N - self.cores and u >= (self.N - (m + self.cores) - 1):
            tmp.append(Reserves(m + self.cores, d, u))
            
        if d > 0:
            tmp.append(Reserves(m, d - 1, u))
            
        if d > 0 and u >= (self.N - m - 2):
            tmp.append(Reserves(m, d - 1, u -1))
            
        if d < u:
            tmp.append(Reserves(m, d + 1, u))
            
        if u >= (self.N - m - 2) and (u - 1) >= d:
            tmp.append(Reserves(m, d, u - 1))
            
        if u < max_u:
            tmp.append(Reserves(m, d, u + 1))
            tmp.append(Reserves(m, d + 1, u + 1))
            
            
        if m > self.cores and d > 0:
            tmp.append(Reserves(m - self.cores, d - 1, u))
            
            
        if u - 1 >= d and u - 1 >= (self.N - (m + self.cores) - 1) and (m + self.cores) < self.N:
            tmp.append(Reserves(m + self.cores, d, u - 1)) 
            
        selected =  random.choice(tmp)
        if selected.U > max_u:
            raise RuntimeError(selected.__str__())      
        return selected.create_solution(self.N, self.nu, self.cost, load)
    
    
        
    def search(self, load, initial_state=None):
        '''
        Simulated annealing algorithm.
        * type load: commons.Load
        * param load: the load parameters
        * rtype: commons.Solution
        '''
        max_iter = 25000
        max_temp = 10000.0
        temp_change = 0.999
        
        temp = max_temp
        
        if initial_state == None:
            initial_state = self.__def_solution(load)
            if initial_state.get_m() % self.cores != 0:
                raise RuntimeError()
            
        sbest = initial_state
        s = initial_state
        ebest = initial_state.get_cost()
        
        
        while self.time < max_iter and s.get_cost() > 0.0:
            snew = self.create_neighbor(s, load)
            if snew.get_d == snew.get_u:
                if snew.get_u >= (self.N - snew.get_m -1):
                    enew = snew.get_cost()
                    temp = temp * temp_change
                    
                    delta_e = exp(s.get_cost() - snew.get_cost()) / temp
                    if delta_e > random.random():
                        s = snew
                    if enew < ebest:
                        sbest = snew
                        ebest = enew
            else:
                enew = snew.get_cost()
                temp = temp * temp_change
                
                tmp1 = exp(s.get_cost() - snew.get_cost()) / temp
                if tmp1 > random.random():
                    s = snew
                if enew < ebest:
                    sbest = snew
                    ebest = enew
                
            self.time += 1
            
        return sbest
                
        
        
        
        
class HillClimbing:
    '''
    Hill climbing search. This algorithm is likely to get stuck in a local
    minima.
    '''

    def __init__(self, N, nu, c1, c2):
        '''
        Constructor
        '''
        self.N = N
        self.nu = nu
        self.costs = commons.Costs(c1, c2)
        
    def cost(self, res, load):
        '''
        Evaluates the cost function for the given parameters.
        '''
        return anor.AnnOperRes(self.N, self.nu, self.costs.c1, self.costs.c2).cost(res, load)
    
    def addToSet(self, s, val):
        #if val not in s:
        #   s.add(val)
        #  return True
        #return False
        return True
    
    
        
    def hillClimbing(self, initialM, initialD, initialU, load):
        '''
        Hill climbing method
        '''
        
        best_configuration = commons.Reserves(initialM, initialD, initialU) # Reserves
        best_cost = self.cost(best_configuration, load) # type EstimatedCost
        
        count = 0
        optimal = False
        cache = set()
        while (optimal == False):
            optimal = True
            
            neighbors = []
            for i in xrange(0, 8):
                tmp = best_configuration
                conf = None
                
                evaluate = False
                if i == 0: # m-1
                    if tmp.m > 0:
                        conf = commons.Reserves(tmp.m-1, tmp.D, tmp.U)
                        evaluate = self.addToSet(cache, conf)
                elif i == 1: # m+1
                    if tmp.m < self.N:
                        conf =  commons.Reserves(tmp.m+1, tmp.D, tmp.U)
                        evaluate = self.addToSet(cache, conf)
                elif i == 2: # D-1
                    if tmp.D > 0:
                        conf =  commons.Reserves(tmp.m, tmp.D-1, tmp.U)
                        evaluate = self.addToSet(cache, conf)
                elif i == 3: # D+1
                    if tmp.D < tmp.U:
                        conf =  commons.Reserves(tmp.m, tmp.D+1, tmp.U)
                        evaluate = self.addToSet(cache, conf)
                elif i == 4: # U-1
                    if tmp.U > tmp.D:
                        conf =  commons.Reserves(tmp.m, tmp.D, tmp.U-1)
                        evaluate = self.addToSet(cache, conf)
                elif i == 5: # U+1
                    conf =  commons.Reserves(tmp.m, tmp.D, tmp.U+1)
                    evaluate = self.addToSet(cache, conf)
                elif i == 6: # m, D+1, U+1
                    conf =  commons.Reserves(tmp.m, tmp.D+1, tmp.U+1)
                    evaluate = self.addToSet(cache, conf)
                elif i == 7: # m, D-1, U-1
                    if tmp.D > 0: # U >= D
                        conf =  commons.Reserves(tmp.m, tmp.D-1, tmp.U-1)
                        evaluate = self.addToSet(cache, conf)
                else:
                    raise BaseException("Unreachable state")
        
                del tmp
                if evaluate == True:                        
                        count += 1
                        cost = self.cost(conf, load)
                        neighbors.append(cost)
                        print cost.__str__()
                    
            for i in xrange(0, len(neighbors)):
                if neighbors[i] is not None:
                    tmp1 = decimal.Decimal(neighbors[i].get_cost())
                    best = decimal.Decimal(best_cost.get_cost())
                    if tmp1.compare(best) <= 0.0:
                        optimal = False
                        best_cost = neighbors[i]
                        best_configuration = neighbors[i].reserves
            
        print("Counter %d\n" % count)
        return best_cost
        
        