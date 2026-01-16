library(arrow)
library(tidyverse)

options(
  readr.show_col_types = FALSE,
  readr.show_progress = FALSE
)

target_year <- 2030
# Can be "LFSolarPV", "Wind_Onshore" or "Wind_Offshore".
source_type <- "LFSolarPV"
pecd_directory <- "Capacity factors/Solar PV"
source_file_pattern <- {
  # The filename pattern for large-scale solar is "…_LFSolarPV_{year}". The only
  # exception is Italy, for which the files are named like "…_Solar PV farm_{year}".
  # We work around this excepting by globbing on "*PV*" instead, which matches both
  # forms.
  if (source_type == "LFSolarPV")
    str_glue("????_CapacityFactors_*PV*_{target_year}.csv")
  else
    str_glue("????_CapacityFactors_{source_type}_{target_year}.csv")
}
parquet_filename <- str_glue("PECD-ERAA2024-{source_type}-{target_year}.parquet")
installed_capacities_filename <- "../pemmdb/ERAA2024 GenerationCapacities.csv"

# Transform a zone identifier to a country code by picking the first
# two letters only.
zone_to_country_code <- \(zone) substr(zone, 1, 2)

# Transform the wide format of the original data into a long
# format with the appropriate column names.
to_long_tibble <- \(.data) {
  .data |>
    separate_wider_delim(Date, ".", names = c("day", "month", NA)) |>
    rename(hour = Hour) |>
    mutate(across(c(day, month), as.numeric)) |>
    pivot_longer(
      !c(hour, day, month, zone),
      names_to = "weather",
      values_to = "cf"
    )
}

load_capacities <- \(target_year) {
  read_csv(installed_capacities_filename) |>
    filter(TARGET_YEAR == target_year, DATA_VERSION == "Post-CfE", STATUS == "Market") |>
    select(
      zone = MARKET_NODE,
      source = TECHNOLOGY,
      cap_MW = CAPACITY_MW
    ) |>
    filter(source %in% c("Solar (PV)", "Wind offshore", "Wind onshore")) |>
    mutate(
      source = case_match(
        source,
        "Solar (PV)" ~ "LFSolarPV",
        "Wind offshore" ~ "Wind_Offshore",
        "Wind onshore" ~ "Wind_Onshore"
      )
    ) |>
    mutate(country = zone_to_country_code(zone)) |>
    filter(cap_MW > 0)
}

read_capacity_factors <- \(filename) {
  zone <- basename(filename) |> substr(1, 4)

  read_csv(filename, skip = 10) |>
    mutate(zone = zone, .before = 1)
}

installed_capacities <- load_capacities(target_year)

# Weigh capacity factors by assumed installed capacities in the target
# year from the "GenerationCapacities" dataset.
all_countries_long <- file.path(pecd_directory, source_file_pattern) |>
  Sys.glob() |>
  map(read_capacity_factors) |>
  list_rbind() |>
  to_long_tibble() |>
  left_join(
    filter(installed_capacities, source == source_type),
    join_by(zone)
  ) |>
  summarise(
    cf = weighted.mean(cf, cap_MW),
    .by = c(country, weather, month, day, hour)
  ) |>
  arrange(country, weather, month, day, hour)

# FIXME: NA country appears in the output.

all_countries_long |>
  write_parquet(parquet_filename)

