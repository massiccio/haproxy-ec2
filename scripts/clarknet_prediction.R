###############################################################################
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
###############################################################################


forecast_clarknet <- function(fin) {
	require(tseries)
	require(forecast)
	
	
	data = read.table(fin, comment.char="#")
	ts = ts(data$V1, frequency=24)
	
	fit = ets(ts, model="MAM", damped=F)
	fcast = forecast(fit, h=1)
	val = fcast$mean[1]
	return(val) # return the forecast
}

args = commandArgs() #1st argument is R or R64, the 2nd is the option (--no-save)
fcast = forecast_clarknet(args[3]) # input and output
write(x=fcast, file=args[4], append=T)