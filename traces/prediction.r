require(tseries)
require(forecast)


data = read.table("trace_clarknet_complete.txt", comment.char="#")
complete = data$V1
start = 243 # the first index in R is 1, not 0
history = complete[1:start]

len = 24

result = array(len)
upper = array(len)
lower = array(len)

error = array(len) # relative forecasting error
actual = array(len)

for (i in 0:len) {
  tmp = complete[1:(start+i)] #c(history, complete[start+i])
  print(length(tmp))
  ts = ts(tmp, frequency=24)
  fit = ets(ts, model="MAM", damped=F)
  fcast = forecast(fit, h=1, level=95) # confidence intervals
  result[i+1] = fcast$mean
  upper[i+1] = fcast$upper
  lower[i+1] = fcast$lower
  
  actual[i+1] = complete[start+i+1]
  error[i+1] = (fcast$mean - complete[start+i+1]) / fcast$mean
  
  cat(1.5*actual[i+1], "\t", 1.5*result[i+1], "\n")
}

cat("avg error ", mean(error)*100)
