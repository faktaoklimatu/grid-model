#!/bin/bash

# Exit on first error.
set -e

scenarios=(2028-{base,base-plus,ex-seven,ex-seven-suas,stress})
num_scenarios=${#scenarios[@]}
aggregation_level=none

weather_years=(WS{01,04,13,16,27,36})
# For dispatch SVGs during a Dunkelflaute episode:
# weather_years=(WS13)

# Uncomment for plotting final SVG hourly plots.
# final_plots="--final-plots --load-solution --group-colors"

common_arguments="--verbose --aggregation-level $aggregation_level --lignite-price-groups $final_plots"

echo "Running all coal scenarios..."

idx=1
num_runs=$((num_scenarios * ${#weather_years[@]}))
for weather_year in "${weather_years[@]}"; do
    for scenario in "${scenarios[@]}"; do
        name="coaldown2+weather-$weather_year"
        echo "Dispatch optimization $idx/$num_runs: $scenario, weather $weather_year"
        idx=$((idx + 1))
        if [[ -d "output/$name/$scenario" && -z "$final_plots" ]]; then
            echo "Outputs have already been generated, skipping"
            continue
        fi
        time ./run_coal_single.py \
            "$scenario" \
            --name "$name" \
            --pecd-year $weather_year \
            $common_arguments
    done
done

echo "All done"

