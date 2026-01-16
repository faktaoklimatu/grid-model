library(arrow)
library(tidyverse)

options(
  readr.show_col_types = FALSE,
  readr.show_progress = FALSE
)

target_year <- 2035
demand_directory <- "Demand/Gross Demand"
# Input columns: Date, Month, Day, Hour, WS*
input_filename_pattern <- str_glue("????_Demand_gross_{target_year}.csv")
# Output columns: country, weather, month, day, hour, dem_MW
parquet_filename <- str_glue("PECD-country-demand_national_estimates-{target_year}.parquet")

# Transform a zone identifier to a country code by picking the first
# two letters only.
zone_to_country_code <- \(zone) substr(zone, 1, 2)

read_demand <- \(filename) {
  country <- basename(filename) |> substr(1, 2)

  df_raw <- read_csv(filename) |>
    select(!Date) |>
    rename(month = Month, day = Day, hour = Hour)

  min_month <- min(df_raw$month)

  df_raw |>
    # For some reason, months and hours start at 0 in PECD v4.1 demand.
    # However, they both start at 1 in the renewables generation time
    # series. Work around the incosistency here by shifting the month
    # and hour number by 1.
    # Moreover, for some even more bizzare reason reason, in Greece's
    # slice of the data, months start at 1. Attempt to fix this
    # incosistency here in a somewhat generic way.
    mutate(month = month + (1 - min_month), hour = 1 + hour) |>
    mutate(country = country, .before = 1) |>
    pivot_longer(
      starts_with("WS"),
      names_to = "weather",
      values_to = "dem_MW"
    )
}

all_countries_long <- str_glue("{demand_directory}/{input_filename_pattern}") |>
  Sys.glob() |>
  map(read_demand) |>
  list_rbind() |>
  # Sum demand across zones within a single country.
  summarise(
    dem_MW = sum(dem_MW),
    .by = c(country, weather, month, day, hour)
  ) |>
  arrange(country, weather, month, day, hour)

all_countries_long |>
  write_parquet(parquet_filename)

