library(arrow)
library(tidyverse)

options(
  readr.show_col_types = FALSE,
  readr.show_progress = FALSE
)

weather_directory <- "PECD - weather/Projected/SP245"
input_filename_pattern <- "*/Population weighted temperature/*.csv"
parquet_filename <- "PECD-ERAA2025-temperatures.parquet"

# Transform a zone identifier to a country code by picking the first
# two letters only.
zone_to_country_code <- \(zone) substr(zone, 1, 2)

read_temperatures <- \(filename, zone = NULL) {
  stopifnot("Zone code must be selected" = !is.null(zone))

  ws_start <- basename(filename) |>
    str_extract("(CMR5|ECE3|MEHR)") |>
    case_match(
      "CMR5" ~ 1,
      "ECE3" ~ 13,
      "MEHR" ~ 25
    )

  stopifnot("Could not match model name" = !is.na(ws_start))

  read_csv(filename, skip = 52) |>
    select(Date, !!zone) |>
    mutate(
      year = year(Date),
      month = as.integer(month(Date)),
      day = as.integer(day(Date)),
      # Unify with other datasets that start the day at hour 1.
      hour = as.integer(1 + hour(Date)),
      .before = Date
    ) |>
    # The weather scenarios correspond to the years 2025–36 in the climate
    # model outputs.
    # TODO: Should we skip leap days as well? How is the demand series (which
    # does not contain leap days) constructed?
    filter(between(year, 2025, 2036)) |>
    # Transform simulated year to weather scenario identifier.
    mutate(
      weather = paste0("WS", ws_start + year - 2025),
      .before = year
    ) |>
    select(!c(Date, year)) |>
    pivot_longer(
      !weather:hour,
      names_to = "country",
      values_to = "temperature"
    )
}

all_ws_long <- file.path(weather_directory, input_filename_pattern) |>
  Sys.glob() |>
  map(~ read_temperatures(.x, "CZ00")) |>
  list_rbind() |>
  mutate(country = zone_to_country_code(country)) |>
  select(country, weather, month, day, hour, temperature) |>
  arrange(country, weather, month, day, hour)

all_ws_long |>
  write_parquet(parquet_filename)

