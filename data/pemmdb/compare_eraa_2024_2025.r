library(tidyverse)

target_year <- 2028

scale_fill_source <- function() {
  scale_fill_manual(
    "",
    values = c(
      Battery = "powderblue",
      "Bio+Geo+WtE+H2" = "cadetblue",
      Coal = "black",
      DSR = "navajowhite",
      Gas = "rosybrown",
      Hydro = "darkblue",
      Nuclear = "slategrey",
      "Other Fossil" = "tan",
      Solar = "gold",
      Wind = "steelblue"
    )
  )
}

pemmdb_2024 <- read_csv("ERAA2024 GenerationCapacities.csv") |>
  filter(
    TARGET_YEAR == .env$target_year,
    DATA_VERSION == "Post-CfE",
    STATUS == "Market"
  ) |>
  mutate(
    Source = case_match(
      TECHNOLOGY,
      c("Biofuel", "Geothermal", "Others (RES)", "Small biomass") ~
        "Bio+Geo+WtE+H2",
      c("Hard coal", "Lignite") ~ "Coal",
      c("Oil", "Others (non-RES)") ~ "Other Fossil",
      c("Implicit solar PV", "Solar (PV)", "Solar (thermal)") ~ "Solar",
      c("Wind offshore", "Wind onshore") ~ "Wind",
      c("Closed loop pumping", "Open loop pumping", "Pondage", "Reservoir",
        "Run of river") ~ "Hydro",
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

pemmdb_2025 <- read_csv("ERAA2025 GenerationCapacities.csv") |>
  filter(
    `Target year` == .env$target_year,
    (Market_Node == "PL00" & data_version == "ERAA 2025 pre-CfE") |
      (Market_Node != "PL00" & data_version == "ERAA 2025 post-CfE"),
    (Operational_Status %in% c("Available on market", "Inelastic supply / fixed profile")) |
      (str_detect(Technology, "PV") &
        Operational_Status == "Out of market – for PV/battery dispatch optimization")
  ) |>
  mutate(
    Source = case_match(
      Technology,
      c("Biofuel", "Geothermal", "Hydrogen", "Small biomass", "Waste") ~
        "Bio+Geo+WtE+H2",
      c("Hard coal", "Lignite") ~ "Coal",
      c("Heavy oil", "Light oil", "Shale oil") ~ "Other Fossil",
      c(
        "Solar PV utility non-tracking", "Solar PV utility tracking",
        "Solar PV rooftop residential", "Solar PV rooftop industrial"
      ) ~ "Solar",
      c("Wind offshore fixed", "Wind offshore floating", "Wind onshore") ~
        "Wind",
      c(
        "Closed loop pumping", "Open loop pumping", "Pondage", "Reservoir",
        "Run of river"
      ) ~ "Hydro",
      c("Battery utility scale", "Battery residential") ~ "Battery",
      "Natural gas" ~ "Gas",
      c("DSR", "Nuclear") ~ Technology,
      # Other:
      # "Solar thermal with storage"    "Solar thermal without storage"
      # "Electrolyser" "Hydrogen" "Power to heat"
    ),
    Country = substr(Market_Node, 0, 2)
  ) |>
  summarise(
    Capacity = sum(Value) / 1e3,
    .by = c(Country, Source)
  ) |>
  filter(
    Country != "TR",
    Country != "UK",
    !is.na(Source)
  )

caps_joint <- pemmdb_2024 |>
  full_join(
    pemmdb_2025,
    join_by(Country, Source),
    suffix = c("_2024", "_2025")
  ) |>
  replace_na(list(Capacity_2024 = 0, Capacity_2025 = 0))

# Absolute changes.
caps_joint |>
  ggplot(aes(Capacity_2025 - Capacity_2024, fct_rev(Country))) +
  geom_col(aes(fill = Source)) +
  scale_fill_source() +
  labs(
    x = "Difference in capacity, 2025 \u2212 2024 (GW)",
    y = "Country",
    subtitle = str_glue("ERAA target year {target_year}")
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom",
    panel.grid.major.y = element_line(linetype = "dotted")
  )

# Dispatchable only.
caps_joint |>
  filter(
    Source %in% c("Bio+Geo+WtE+H2", "Coal", "Gas", "Nuclear", "Other Fossil")
  ) |>
  mutate(Diff = Capacity_2025 - Capacity_2024) |>
  group_by(Country) |>
  # Keep only countries where all changes (in either direction) are
  # at least 2 GW.
  group_map(~ if (sum(abs(.x$Diff)) < 2) tibble() else .x, .keep = TRUE) |>
  list_rbind() |>
  ggplot(aes(Diff, fct_rev(Country))) +
  geom_col(aes(fill = Source)) +
  geom_vline(xintercept = 0, colour = "white") +
  stat_summary(
    fun = sum,
    geom = "point",
    shape = 21,
    colour = "white",
    fill = "black",
    size = 2.5,
    stroke = .6
  ) +
  scale_fill_source() +
  labs(
    x = "Difference in capacity, 2025 \u2212 2024 (GW)",
    y = "Country",
    subtitle = str_glue(
      "ERAA target year {target_year}, dispatchable only, excl. countries",
      " with diff < 2 GW"
    )
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom",
    panel.grid.major.y = element_line(linetype = "dotted")
  )

# Relative (%) changes, excluding small values.
caps_joint |>
  filter(Capacity_2025 > 1, Capacity_2024 > 1) |>
  mutate(ChangePct = 100 * (Capacity_2025 / Capacity_2024 - 1)) |>
  filter(abs(ChangePct) >= 5) |>
  ggplot(aes(ChangePct, fct_rev(Country))) +
  geom_col(aes(fill = Source)) +
  scale_fill_source() +
  labs(
    x = "Difference in capacity, 2025 : 2024 (%)",
    y = "Country",
    subtitle = str_glue(
      "ERAA target year {target_year}, excl. sources < 1 GW and changes < 5%"
    )
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom",
    panel.grid.major.y = element_line(linetype = "dotted")
  )

filter(caps_joint, Country == "CZ")
filter(caps_joint, Source == "Gas", Country %in% c("ES", "FR", "IT"))
filter(caps_joint, Source == "Solar", Country %in% c("IT", "NL"))
