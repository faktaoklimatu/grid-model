from energy_insights.region import *
from energy_insights.sources.basic_source import BasicSourceType
from energy_insights.sources.flexible_source import FlexibleSourceType

scenarios = [
    {
        "name": "cz-2030-basic",
        "countries": {
            CZECHIA: {
                "load_factors": {
                    "load_base": 1.2,
                    "heat_pumps_share": (0.01, 0.1),
                    "heat_pumps_cooling_share": (0.2, 0.3),
                },
                "basic_sources": {
                    BasicSourceType.SOLAR: {"capacity_mw": 10_580},
                    BasicSourceType.ONSHORE: {"capacity_mw": 1_000},
                    BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
                    BasicSourceType.HYDRO: {"capacity_mw": 1_105},
                },
                'flexible_sources': {
                    FlexibleSourceType.SOLID_BIOMASS: {
                        'capacity_mw': 800,
                        'max_total_twh': 4.2,
                    },
                    FlexibleSourceType.BIOGAS: {
                        'capacity_mw': 323 * 0.3,
                        'max_total_twh': 2.5 * 0.3,
                    },
                    FlexibleSourceType.LIGNITE: {
                        'capacity_mw': 4_000,
                    },
                    FlexibleSourceType.COAL: {
                        'capacity_mw': 700,
                    },
                    FlexibleSourceType.WASTE: {
                        'capacity_mw': 60,
                    },
                    FlexibleSourceType.GAS_CCGT: {
                        'capacity_mw': 2_400,
                    },
                    FlexibleSourceType.GAS_ENGINE: {
                        'capacity_mw': 600,
                    },
                },
                "storage": "cz-2030-basic",
            },
        }
    },
    {
        "name": "cz-de-2030-basic",
        "countries": {
            CZECHIA: {
                "load_factors": {
                    "load_base": 1.2,
                    "heat_pumps_share": (0.01, 0.1),
                    "heat_pumps_cooling_share": (0.2, 0.3),
                },
                "basic_sources": {
                    BasicSourceType.SOLAR: {"capacity_mw": 10_580},
                    BasicSourceType.ONSHORE: {"capacity_mw": 1_000},
                    BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
                    BasicSourceType.HYDRO: {"capacity_mw": 1_105},
                },
                'flexible_sources': {
                    FlexibleSourceType.SOLID_BIOMASS: {
                        'capacity_mw': 800,
                        'max_total_twh': 4.2,
                    },
                    FlexibleSourceType.BIOGAS: {
                        'capacity_mw': 323 * 0.3,
                        'max_total_twh': 2.5 * 0.3,
                    },
                    FlexibleSourceType.LIGNITE: {
                        'capacity_mw': 4_000,
                    },
                    FlexibleSourceType.GAS_CCGT: {
                        'capacity_mw': 2_400,
                    },
                },
                "storage": "cz-2030-basic",
            },
            GERMANY: {
                "load_factors": {
                    "load_base": 1.2,
                    "heat_pumps_share": (0.01, 0.1),
                    "heat_pumps_cooling_share": (0.2, 0.3),
                },
                "basic_sources": {
                    BasicSourceType.SOLAR: {"capacity_mw": 193_600},
                    BasicSourceType.ONSHORE: {"capacity_mw": 109_700},
                    BasicSourceType.OFFSHORE: {"capacity_mw": 30_200},
                    BasicSourceType.HYDRO: {"capacity_mw": 4_937},
                },
                'flexible_sources': {
                    FlexibleSourceType.SOLID_BIOMASS: {
                        'capacity_mw': 6_129,
                        'max_total_twh': 70,
                    },
                    FlexibleSourceType.LIGNITE: {
                        'capacity_mw': 9_000,
                    },
                    FlexibleSourceType.COAL: {
                        'capacity_mw': 8_000,
                    },
                    FlexibleSourceType.GAS_PEAK: {
                        'capacity_mw': 14_000,
                    },
                    FlexibleSourceType.GAS_CCGT: {
                        'capacity_mw': 39_000,
                    },
                },
                "storage": "de-2030",
            }
        },
        "interconnectors": "2030",
    },
    {
        "name": "cz-2050-nuclear",
        "countries": {
            CZECHIA: {
                "load_factors": {
                    "load_base": 1.4,
                    "heat_pumps_share": (0.01, 0.15),
                    "heat_pumps_cooling_share": (0.2, 0.3),
                },
                "basic_sources": {
                    BasicSourceType.SOLAR: {"capacity_mw": 9_460},
                    BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
                    BasicSourceType.NUCLEAR: {"capacity_mw": 6_560},
                    BasicSourceType.HYDRO: {"capacity_mw": 1_105},
                },
                'flexible_sources': {
                    FlexibleSourceType.GAS_CCGT_CCS: {
                        'capacity_mw': 2_000
                    },
                    FlexibleSourceType.SOLID_BIOMASS: {
                        'capacity_mw': 2_500,
                        'max_total_twh': 8,
                    },
                    FlexibleSourceType.BIOGAS_PEAK: {
                        'capacity_mw': 5_000,
                        'max_total_twh': 3,
                    },
                },
                "storage": "cz-2050-nuclear",
            },
        }
    },
]
