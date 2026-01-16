library(tidyverse)

pemmdb_2023 <- readxl::read_excel(
  "ERAA2023 PEMMDB Generation.xlsx",
  sheet = "TY2028",
  skip = 1,
  n_max = 24
) |>
  rename(Source = 1) |>
  filter(
    str_detect(Source, "Biofuel|Coal|Gas|Lignite|Nuclear|Oil|^Others|^Solar|^Wind|Turbine|Response|Offtake")
  ) |>
  pivot_longer(!Source, names_to = "Region", values_to = "Capacity") |>
  mutate(
    Source = case_when(
      Source %in% c("Biofuel", "Others renewable") ~ "Bioenergy",
      Source %in% c("Hard Coal", "Lignite") ~ "Coal",
      Source %in% c("Oil", "Others non-renewable") ~ "Other Fossil",
      str_starts(Source, "Solar") ~ "Solar",
      str_starts(Source, "Wind") ~ "Wind",
      str_detect(Source, "Turbine") ~ "Hydro",
      str_starts(Source, "Batteries") ~ "Battery",
      str_starts(Source, "Demand Side Response") ~ "DSR",
      .default = str_trim(Source)
    ),
    Country = substr(Region, 0, 2)
  ) |>
  summarise(
    Capacity = sum(Capacity) / 1e3,
    .by = c(Country, Source)
  ) |>
  filter(Country != "UK")

pemmdb_2024 <- read_csv("ERAA2024 GenerationCapacities.csv") |>
  filter(
    TARGET_YEAR == 2028,
    DATA_VERSION == "Post-CfE",
    STATUS == "Market"
  ) |>
  mutate(
    Source = case_match(
      TECHNOLOGY,
      c("Biofuel", "Geothermal", "Others (RES)", "Small biomass") ~ "Bioenergy",
      c("Hard coal", "Lignite") ~ "Coal",
      c("Oil", "Others (non-RES)") ~ "Other Fossil",
      c("Implicit solar PV", "Solar (PV)", "Solar (thermal)") ~ "Solar",
      c("Wind offshore", "Wind onshore") ~ "Wind",
      c("Closed loop pumping", "Open loop pumping", "Pondage", "Reservoir", "Run of river") ~ "Hydro",
      c("Battery", "Gas", "Nuclear") ~ TECHNOLOGY,
      "DSR" ~ "DSR"
    ),
    Country = substr(MARKET_NODE, 0, 2)
  ) |>
  summarise(
    Capacity = sum(CAPACITY_MW) / 1e3,
    .by = c(Country, Source)
  ) |>
  filter(
    Country != "TR",
    Country != "UK",
    !is.na(Source)
  )

caps_joint <- pemmdb_2023 |>
  full_join(
    pemmdb_2024,
    join_by(Country, Source),
    suffix = c("_2023", "_2024")
  ) |>
  replace_na(list(Capacity_2023 = 0, Capacity_2024 = 0))

caps_joint |>
  ggplot(aes(Capacity_2024 - Capacity_2023, fct_rev(Country))) +
  geom_col(aes(fill = Source)) +
  scale_fill_manual(
    "",
    values = c(
      Battery = "powderblue",
      Bioenergy = "cadetblue",
      Coal = "black",
      DSR = "navajowhite",
      Gas = "rosybrown",
      Hydro = "darkblue",
      Nuclear = "slategrey",
      "Other Fossil" = "tan",
      Solar = "gold",
      Wind = "steelblue"
    )
  ) +
  labs(
    x = "Difference in capacity, 2024 \u2212 2023 (GW)",
    y = "Country"
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom",
    panel.grid.major.y = element_line(linetype = "dotted")
  )

filter(caps_joint, Country == "CZ")
filter(caps_joint, Source == "Gas", Country %in% c("ES", "FR", "IT"))
filter(caps_joint, Source == "Solar", Country %in% c("IT", "NL"))
