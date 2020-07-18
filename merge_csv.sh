#!/usr/bin/env bash

#SBATCH --job-name=minibench-pp
#SBATCH --cpus-per-task=1
#SBATCH --mem=4096
#SBATCH --nodelist=critical001

OutFileName="./results/stats.csv"                       # Fix the output name
i=0                                       # Reset a counter
for filename in ./results/*_stats.csv; do 
	if [ "$filename"  != "$OutFileName" ] ;      # Avoid recursion 
	then 
		if [[ $i -eq 0 ]] ; then 
			head -1  "$filename" >   "$OutFileName" # Copy header if it is the first file
		fi
		tail -n +2  "$filename" >>  "$OutFileName" # Append from the 2nd line each file
		i=$(( $i + 1 ))                            # Increase the counter
	fi
done

