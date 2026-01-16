library(arrow)
library(tidyverse)

options(
  readr.show_col_types = FALSE,
  readr.show_progress = FALSE
)

target_year <- 2030
inflows_directory <- "Hydro Inflows"
input_filename_pattern <- \(source_type) str_glue("????_Hydro_Inflows_{source_type}_{target_year}.csv")
parquet_filename <- \(source_type) str_glue("PECD-ERAA2024-{source_type}-inflows-{target_year}.parquet")

# Transform a zone identifier to a country code by picking the first
# two letters only.
zone_to_country_code <- \(zone) substr(zone, 1, 2)

to_long_tibble <- \(.data) {
  time_col <- if_else(has_name(.data, "WEEK"), "WEEK", "DAY")
  .data |>
    pivot_longer(
      !c(country, !!time_col),
      names_to = "weather",
      values_to = "gen_GWh"
    ) |>
    # The original data is in MWh.
    mutate(gen_GWh = gen_GWh / 1000)
}

read_inflows <- \(filename) {
  country <- basename(filename) |> substr(1, 2)

  read_csv(filename) |>
    mutate(country = country, .before = 1)
}

# Run-of-river and pondage hydro.
all_ror_long <- file.path(inflows_directory, input_filename_pattern("HRR")) |>
  Sys.glob() |>
  map(read_inflows) |>
  list_rbind() |>
  to_long_tibble() |>
  na.omit() |>
  rename(Day = DAY) |>
  summarise(gen_GWh = sum(gen_GWh), .by = c(country, weather, Day)) |>
  arrange(country, weather, Day) |>
  mutate(technology = "ror")

all_pondage_long <- file.path(inflows_directory, input_filename_pattern("HPI")) |>
  Sys.glob() |>
  map(read_inflows) |>
  list_rbind() |>
  to_long_tibble() |>
  na.omit() |>
  rename(Day = DAY) |>
  summarise(gen_GWh = sum(gen_GWh), .by = c(country, weather, Day)) |>
  arrange(country, weather, Day) |>
  mutate(technology = "pondage")

bind_rows(all_ror_long, all_pondage_long) |>
  write_parquet(parquet_filename("RoR+pondage"))

# Pumped open-loop storage and reservoir hydro.
all_open_long <- file.path(inflows_directory, input_filename_pattern("HOL")) |>
  Sys.glob() |>
  map(read_inflows) |>
  list_rbind() |>
  to_long_tibble() |>
  na.omit() |>
  rename(Week = WEEK) |>
  summarise(inflow_GWh = sum(gen_GWh), .by = c(country, weather, Week)) |>
  arrange(country, weather, Week) |>
  mutate(technology = "pumped_open")

all_reservoir_long <- file.path(inflows_directory, input_filename_pattern("HRI")) |>
  Sys.glob() |>
  map(read_inflows) |>
  list_rbind() |>
  to_long_tibble() |>
  na.omit() |>
  rename(Week = WEEK) |>
  summarise(inflow_GWh = sum(gen_GWh), .by = c(country, weather, Week)) |>
  arrange(country, weather, Week) |>
  mutate(technology = "reservoir")

bind_rows(all_open_long, all_reservoir_long) |>
  write_parquet(parquet_filename("reservoir+pumped"))

