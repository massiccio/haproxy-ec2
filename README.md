haproxy-ec2
===========

The provided code does provides the following functionalities:
- Monitors the status of a haproxy instance sitting in front of a cluster of servers running on Amazon EC2 and starts/stops them according to the observed load.
- Starts and sets up a cluster of Apache servers, with one back end server running MySQL and Memcached (all services are auto-configured).
- Sets up a client code which can be used to load test the above cluster.

*This is the code I have written to run the experiments described in the paper <a href="http://math.ut.ee/~mazzucco/papers/greenmetrics.pdf">"Empirical Evaluation of Power Saving Policies for Data Centers"<a/>, published at ACM Greenmentrics 2012*

Requirements
------------

- Python >= 2.6
- Amazon EC2 account
- AMIs to run MySQL, Memcached, Apache, and HAProxy (tested with HAProxy 1.4.20)
- <a href="https://github.com/boto/boto">Boto</a> to interact with Amazon EC2
- <a href="http://www.numpy.org/">Numpy</a> to solve the numerical routines.
Numpy is used only by the zeros() function in the anor.anor module, which can be easily modified, and by the utils.log_analyzer module. Hence, with a bit of work, it is easy to remove the dependency on Numpy.
- The stats module requires the <a href="http://code.google.com/p/psutil/">psutil<a/> library to gather OS related metrics (e.g., CPU usage). This is only a monitoring module though, and it is not used by anything else. Also, one can easily remove this dependency, e.g., by parsing the /proc filesystem on Linux (the state should be maintained as /proc values are counters).
- The client code employs the <a href="https://github.com/Lispython/human_curl">human_curl<a/> library. The init_ec2.py script takes care of setting up this library on the client virtual machine.


Code Description
----------------

- main: script used to monitor HAProxy. It should be run on the host running HAProxy. This script is auto-configuring, meaning that it queries AWS go obtain the IP addresses of the Apache instances, and configures HAProxy accordingly. See the code for a complete description of the required parameters (cost, number of reserves, etc.). Example invocation:

  ```bash
  sudo python monitor.py -mu 10 -m 0 -D 0 -U 0 -c1 1.0 -c2 1.0
  ```

- init_ec2: script used to start and configure all the EC2 instances. Arguments:
  1. -n = number of Apache instances to launch (default = 1)
  2. -key = path to the key (defualt = ~/.ssh/haproxy-key.pem)
  3. -r = False to launch new instances and configure them, True for configuring only the instances (i.e., start the services, as the instances have already been launched).

  ```bash
  python init_ec2.py -n 20 -key ~/.ssh/haproxy-key.pem -r True
  ```
  
Apart from the Apache servers, specified by the -n parameter, the following instances are started and configured:
  1. HAProxy: 1 server
  2. Memcached + MySQL: 1 server
  3. Load generator: 1 server


The typical workflow is the following:

  1. invoke init_ec2 to set up the cluster: a number of constants need to be set in the code in order to specify the AMIs, etc. Regarding the MySQL AMI, Wikipedia dumps can be downloaded from <a href="http://dumps.wikimedia.org/">here</a>.
  2. log in to the HAProxy instance and start main.py
  3. log in to the client and start the load generator.

**Note: There is a big hit in network latency between using internal and public IP address. If you communicate between instances using public or elastic IP address even in the same region you pay regional data transfer rates. See <a href="http://www.cloudiquity.com/2009/02/using-amazon-ec2-public-ip-address-inside-ec2-network/">here</a> for more information.**

*Also, please note that this load generator is not able to produce a lot of traffic (i.e., thousands of requests per second). I have implemented a client using both the Twisted and Tornado frameworks (including the use of the reactor pattern) and obtained similar results. In order to squeeze that amount of performance out of Python one should probably deal with sockets, etc. The Java code I have developed <a href="https://github.com/massiccio/java/tree/master/src/http">here</a>, however, does not have this kind of problems.*


Apart from the above scripts, the following code is included into this repository.

- utils.log_analyzer: analyzes HAProxy logs and prints mean, variance, minimum, maximum, and squared coefficient of variation of service times and response times. It also reports the number and kind of errors (e.g., HTTP 500 status).

- monitor.stats: provides code to monitor the resource utilization of localhost
  1.  Network: bytes in and out. Data collected from /proc/net/dev on Linux and netstat -b -I iface on Max OS X.
  2.  CPU usage: data from psutil 
  3.  number of connections: polls HAProxy. Note: requires the same privileges as those of the HAProxy process.
  4.  Unix load
  5.  memory usage: data from psutil
  6.  arrival rate: number of jobs entering the system per second
  7.  cost: number of jobs in the system, average arrival rate, number of servers (active and running jobs), cost (current, average, and total), and queue parameters (number of reserves as well as the two thresholds employed to power up/down the reserves). The cost is defined in Equation (1) of the <a href="http://math.ut.ee/~mazzucco/papers/greenmetrics.pdf">paper</a>.
  8.  HAProxy: most of the metrics described in Section 9.1 of the HAProxy <a href="http://haproxy.1wt.eu/download/1.4/doc/configuration.txt">documentation</a>.

- monitor.socket_haproxy: employs the code of monitor.stats to monitor HAProxy (i.e., it connects to HAProxy and reports the HAProxy statistics described above). Most of this code is based on <a href="http://feurix.org/projects/hatop/">HATop</a>.

- monitor.commons: contains classes used to store data about running instances.

- monitor.haproxy_configuration: code used to manage the configuration of HAProxy, including reload the process. Assumes that the 'haproxy' binary is in the path.
- interface_to_r: code invoking the scripts in the scripts folder. This is an example showing how to invoke R to predict time series.

- client: client code.

