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

@author: michele
'''

import anor
import decimal


class Costs:
    '''
    Holding cost and electricity cost per unit time
    '''
    def __init__(self, c1, c2):
        '''
        :param c1: holding cost (float)
        :param c2: server cost (float)
        '''
        self.c1 = c1
        self.c2 = c2
        
    def get_c1(self):
        return self.c1
    
    def get_c2(self):
        return self.c2
        
    def __str__(self):
        return "c1 = " + self.c1 + ", c2 = " + self.c2
    

class Load:
    
    def __init__(self, lam, mu):
        '''
        Load parameters, arrival rate and service rate
        '''
        self.lam = lam
        self.mu = mu
       
       
    def get_lam(self):
        return self.lam
    
    def get_mu(self):
        return self.mu
   
    def get_load(self):
        '''
        Gets the load, as lambda / mu
        ''' 
        return self.lam / self.mu
    
    def __str__(self):
        return 'Arr. rate: %.2f, serv. rate %.2f, load %.2f' % (self.lam, self.mu, self.get_load())
    
    
    
class Reserves:
    '''
    Reserves, i.e., triple(m, D, U)
    '''
    def __init__(self, m=0, D=0, U=0):
        '''
        * The number of reserves
        * The lower threshold
        * The upper threshold
        '''
        if m < 0:
            raise ValueError('m cannot be negative %d' % m)
        if D < 0:
            raise ValueError('D cannot be negative %d' % D)
        if U < D:
            raise ValueError('U cannot smaller than D: U %d, D %d' % U, D)
        self.m = m
        self.D = D
        self.U = U
        
        
    def create_solution(self, N, nu, cost, load):
        '''
        Creates a solution object
        '''
        c = anor.AnnOperRes(N, nu, cost.get_c1(), cost.get_c2())
        return c.cost(self, load)
        
    def __key(self):
        return (self.m, self.D, self.U)
        
    def __hash__(self):
        return hash(self.__key())
    
    def __str__(self):
        return "m=%d, D=%d, U=%d" % (self.m, self.D, self.U) 
    
    def __eq__(self, other):
        if not isinstance(other, Reserves):
            return False
        if self.D != other.D:
            return False
        if self.U != other.U:
            return False
        if self.m != other.m:
            return False
        
    def __cmp__(self, other):
        if self.m < other.m:
            return -1
        elif self.m > other.m:
            return 1
        else:
            if self.U < other.U:
                return -1
            elif self.U > other.U:
                return 1
            else:
                if self.D < other.D:
                    return -1
                elif self.D > other.D:
                    return 1
                else:
                    return 0
                
                
class Solution:
    '''
    Solution of the search methods
    '''
    def __init__(self, cost, reserves=Reserves(0,0,0)):
        self.cost = cost
        self.reserves = reserves
        
    
    def get_cost(self):
        '''
        Gets the cost of this solution
        '''
        return self.cost    
    
    
    def get_m(self):
        '''
        Gets the number of reserves
        '''
        return self.reserves.m
    
    
    def get_d(self):
        '''
        Gets the lower threshold, D
        '''
        return self.reserves.D
    
    
    def get_u(self):
        '''
        Gets the upper threshold, U
        '''
        return self.reserves.U
    
    
    def get_reserves(self):
        '''
        Gets the Reserves
        * rtype: Reserves
        '''
        return self.reserves
    
    
    def __str__(self):
        '''
        Returns a string representation of this cost object
        '''
        return "Cost %s, cost %.10f" % (self.reserves.__str__(), self.cost)
    
    
    def __key(self):
        # the cost is not necessary
        return (self.reserves.m, self.reserves.D, self.reserves.U)
    
        
    def __hash__(self):
        return hash(self.__key())

    
    def __eq__(self, other):
        if not isinstance(other, Reserves):
            return False
        if self.reserves.D != other.D:
            return False
        if self.reserves.U != other.U:
            return False
        if self.reserves.m != other.m:
            return False
        
        
        
    def __cmp__(self, other):
        '''
        Compares the cost fields
        '''
        if isinstance(other, Solution):
            tmp1 = decimal.Decimal(self.cost)
            tmp2 = decimal.Decimal(other.cost)
            return tmp1.compare(tmp2)
        raise BaseException("Expected EstimatedCost object")

            
