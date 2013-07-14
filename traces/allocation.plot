set terminal postscript eps enhanced color "Times" 24

set output "allocations.eps"

plot "allocations_day_10.txt" index 0 w steps lw 4 t "Oracle",\
"" index 1 w steps lw 4 lc rgb "forest-green" t "MAM"