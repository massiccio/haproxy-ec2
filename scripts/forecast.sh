#!/bin/bash

command='unknown'
unamestr=`uname`
if [[ "$unamestr" == 'Darwin' ]]; then
   command='R64'
elif [[ "$unamestr" == 'Linux' ]]; then
   command='R'
else 
	echo "Unrecognized system"
	exit 1
fi

# try to execute the command as
# nice -n 10 ..... so that R will not use all the CPU (the process will have lower priority)

# $1 is the file containing the data, $2 is the file where the result will be written
$command --no-save < clarknet_prediction.R $1 $2
#echo "Done"
exit 0
