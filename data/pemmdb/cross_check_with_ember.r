library(tidyverse)

country_code_to_region <- function(country_code) {
  case_match(
    country_code,
    "AUT" ~ "AT",
    "BIH" ~ "BA",
    "BEL" ~ "BE",
    "BGR" ~ "BG",
    "CHE" ~ "CH",
    "CYP" ~ "CY",
    "CZE" ~ "CZ",
    "DEU" ~ "DE",
    "DNK" ~ "DK",
    "EST" ~ "EE",
    "ESP" ~ "ES",
    "FIN" ~ "FI",
    "FRA" ~ "FR",
    "GRC" ~ "GR",
    "HRV" ~ "HR",
    "HUN" ~ "HU",
    "IRL" ~ "IE",
    "ITA" ~ "IT",
    "LTU" ~ "LT",
    "LUX" ~ "LU",
    "LVA" ~ "LV",
    "MNE" ~ "ME",
    "MKD" ~ "MK",
    "MLT" ~ "MT",
    "NLD" ~ "NL",
    "NOR" ~ "NO",
    "POL" ~ "PL",
    "PRT" ~ "PT",
    "ROU" ~ "RO",
    "SRB" ~ "RS",
    "SWE" ~ "SE",
    "SVN" ~ "SI",
    "SVK" ~ "SK"
  )
}

pemmdb <- readxl::read_excel(
  "ERAA2023 PEMMDB Generation.xlsx",
  sheet = "TY 2025",
  skip = 1,
  n_max = 24
) |>
  rename(Source = 1) |>
  filter(str_detect(Source, "Biofuel|Coal|Gas|Lignite|Nuclear|Oil|^Others|^Solar|^Wind")) |>
  pivot_longer(!Source, names_to = "Region", values_to = "Capacity") |>
  mutate(
    Source = case_when(
      Source %in% c("Biofuel", "Others renewable") ~ "Bioenergy",
      Source %in% c("Hard Coal", "Lignite") ~ "Coal",
      Source %in% c("Oil", "Others non-renewable") ~ "Other Fossil",
      str_starts(Source, "Solar") ~ "Solar",
      str_starts(Source, "Wind") ~ "Wind",
      .default = str_trim(Source)
    ),
    Region = substr(Region, 0, 2)
  ) |>
  summarise(
    Capacity = sum(Capacity) / 1e3,
    .by = c(Region, Source)
  ) |>
  filter(Region != "UK")

ember <- read_csv("../yearly_full_release_long_format.csv") |>
  filter(
    Year == 2023,
    Category == "Capacity",
    Variable %in% c("Solar", "Wind", "Nuclear", "Gas", "Coal", "Bioenergy", "Other Fossil", "Other Renewables")
  ) |>
  select(
    CountryCode = `Country code`,
    Source = Variable,
    Capacity = Value
  ) |>
  mutate(Source = if_else(Source == "Other Renewables", "Bioenergy", Source)) |>
  summarise(
    Capacity = sum(Capacity),
    .by = c(CountryCode, Source)
  )

caps_joint <- pemmdb |>
  left_join(
    ember |>
      mutate(Region = country_code_to_region(CountryCode)) |>
      select(!CountryCode),
    join_by(Region, Source),
    suffix = c(".pemmdb", ".ember")
  ) |>
  replace_na(list(Capacity.ember = 0))
# pivot_longer(
#   !Region:Source,
#   names_pattern = "\\.(\\w+)$",
#   names_to = "Database",
#   values_to = "Capacity"
# )

caps_joint |>
  ggplot(aes(Capacity.pemmdb - Capacity.ember, Region)) +
  geom_col(aes(fill = Source)) +
  scale_fill_manual(
    "",
    values = c(
      Bioenergy = "cadetblue",
      Coal = "black",
      Gas = "rosybrown",
      Nuclear = "slategrey",
      "Other Fossil" = "tan",
      Solar = "gold",
      Wind = "cornflowerblue"
    )
  ) +
  theme_minimal() +
  theme(legend.position = "bottom")

filter(caps_joint, Region == "CZ")
filter(caps_joint, Source == "Gas", Region %in% c("ES", "FR", "IT"))
filter(caps_joint, Source == "Solar", Region %in% c("IT", "NL"))
