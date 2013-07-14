set terminal postscript eps enhanced color "Times" 24


#######################################
# Clarket trace
#######################################

set output "clarknet.eps"

#set xrange[0:20000]
set xrange[0:14]
set yrange[0:120]
set mxtics 2
set mytics 2
#set label "(Weekend)" font "Times, 18" at 9000, 350 center
#set label "(Weekend)" font "Times, 18" at 18000, 400 center


# Axes
set style line 11 lc rgb '#808080' lt 1
set border 3 back ls 11
set tics nomirror out scale 0.75
set arrow from graph 1,0 to graph 1.05,0 size screen 0.025,15,60 filled ls 11
#set arrow from graph 0,1 to graph 0,1.05 size screen 0.025,15,60 filled ls 11
# Grid
#set style line 12 lc rgb'#808080' lt 0 lw 1
#set grid back ls 12
# Grid
set style line 12 lc rgb '#ddccdd' lt 1 lw 1.5 # --- red
set style line 13 lc rgb '#ddccdd' lt 1 lw 0.5
set style line 14 lc rgb '#ccdddd' lt 1 lw 1.5 # --- green
set style line 15 lc rgb '#ccdddd' lt 1 lw 0.5
set style line 16 lc rgb '#ddddcc' lt 1 lw 1.5 # --- yellow
set style line 17 lc rgb '#ddddcc' lt 1 lw 0.5
set grid xtics mxtics ytics mytics back ls 12 ls 13


set style line 12 lc rgb'#808080' lt 0 lw 1
set grid back ls 12

set style rect fc lt -1 fs solid 0.15 noborder
set obj rect from 10.15, graph 0 to 11.15, graph 1

set xlabel "Time [day]"
set ylabel "Arr. rate [req/sec]"

set arrow from graph 1,0 to graph 1.05,0 size screen 0.025,15,60 \
    filled ls 11

plot "trace_clarknet_scaled.txt" u ($0/24):($1*1.5) every ::1::243 w lp pointtype 2 lt 1 lc rgb "forest-green" t "",\
"" u (($0/24)+10.15):($1*1.5) every ::244::268 w lp pointtype 5 lt rgb "red" t "",\
"" u (($0/24)+11.18):($1*1.5) every ::268::336 w lp pointtype 2 lt 1 lc rgb "forest-green" t ""


