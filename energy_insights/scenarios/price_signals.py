"""
Provides special optimization runs.
"""

from ..region import *


def get_runs_for_price_signals():
    scenarios = [
        # {  # TODO: Clean up / make work after refactoring. This is tricky w.r.t. "current".
        #     "name": "cee-2020",
        #     "interconnectors": "2021",
        #     "countries": {
        #         CZECHIA: {
        #             'factors': "current",
        #             'flexible_sources': "cz-current",
        #             'storage': "cz-current",
        #         },
        #         GERMANY: {
        #             'factors': "current",
        #             'flexible_sources': "de-current",
        #             'storage': "de-current",
        #         },
        #         AUSTRIA: {
        #             'factors': "current",
        #             'flexible_sources': "at-current",
        #             'storage': "at-current",
        #         },
        #         POLAND: {
        #             'factors': "current",
        #             'flexible_sources': "pl-current",
        #             'storage': "pl-current",
        #         },
        #         SLOVAKIA: {
        #             'factors': "current",
        #             'flexible_sources': "sk-current",
        #             'storage': "sk-current",
        #         },
        #     }
        # },
        {
            "name": "cee-2030-basic",
            "interconnectors": "2030",
            "input_costs": "2030",
            "countries": {
                CZECHIA: {
                    'factors': "cz-2030-basic",
                    'basic_sources': "cz-2030-basic",
                    'flexible_sources': "cz-2030-basic",
                    'storage': "cz-2030-basic",
                },
                GERMANY: {
                    'factors': "de-2030-government-plans-achieved",
                    'basic_sources': "de-2030-government-plans-achieved",
                    'flexible_sources': "de-2030",
                    'storage': "de-2030",
                },
                AUSTRIA: {
                    'factors': "generic-2030-basic",
                    'basic_sources': "at-2030",
                    'flexible_sources': "at-2030",
                    'storage': "at-2030",
                },
                POLAND: {
                    'factors': "generic-2030-basic",
                    'basic_sources': "pl-2030",
                    'flexible_sources': "pl-2030",
                    'storage': "pl-2030",
                },
                SLOVAKIA: {
                    'factors': "generic-2030-basic",
                    'basic_sources': "sk-2030",
                    'flexible_sources': "sk-2030",
                    'storage': "sk-current",
                },
            },
        },
        {
            "name": "cee-2030-advanced",
            "interconnectors": "2030",
            "input_costs": "2030",
            "countries": {
                CZECHIA: {
                    'factors': "cz-2030-advanced",
                    'basic_sources': "cz-2030-advanced",
                    'flexible_sources': "cz-2030-advanced",
                    'storage': "cz-2030-advanced",
                },
                GERMANY: {
                    'factors': "de-2030-government-plans-achieved",
                    'basic_sources': "de-2030-government-plans-achieved",
                    'flexible_sources': "de-2030",
                    'storage': "de-2030",
                },
                AUSTRIA: {
                    'factors': "generic-2030-basic",
                    'basic_sources': "at-2030",
                    'flexible_sources': "at-2030",
                    'storage': "at-2030",
                },
                POLAND: {
                    'factors': "generic-2030-basic",
                    'basic_sources': "pl-2030",
                    'flexible_sources': "pl-2030",
                    'storage': "pl-2030",
                },
                SLOVAKIA: {
                    'factors': "generic-2030-basic",
                    'basic_sources': "sk-2030",
                    'flexible_sources': "sk-2030",
                    'storage': "sk-current",
                },
            },
        }
    ]
    return [
        {
            "config": {
                "year": 2020,
                "analysis_name": "price-signals-2020",
                "filter": {
                    "week_sampling": 4,  # Plot every fourth week in the output.
                },
                "output": {
                    "format": "png",
                    "dpi": 150,
                    "size_y_week": 0.7,
                    "price": True,
                    "parts": ["titles", "weeks", "week_summary", "year_stats"],
                    "regions": "separate",
                },
                "optimize_ramp_up_costs": True,
            },
            "scenarios": scenarios,
        },
        {
            "config": {
                "year": 2019,
                "analysis_name": "price-signals-2019",
                "filter": {
                    "week_sampling": 4,  # Plot every fourth week in the output.
                },
                "output": {
                    "format": "png",
                    "dpi": 150,
                    "size_y_week": 0.7,
                    "price": True,
                    "parts": ["titles", "weeks", "week_summary", "year_stats"],
                    "regions": "separate",
                },
                "optimize_ramp_up_costs": True,
            },
            "scenarios": scenarios,
        }
    ]
