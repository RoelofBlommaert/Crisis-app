"""
Shared country list for the Crisis & Connectivity Monitor data pulls.

Countries were chosen to mix genuinely crisis-relevant destinations with
enough overlap against CBS's outbound-travel table to be useful. CBS
(table 84365NED) only breaks out ~15 individual "most visited" countries;
everything else is only available at continent/region level. Where a
country isn't broken out individually, `cbs_key` points to the broadest
region CBS does report, and `cbs_granularity` records how coarse that is
so the merge step (and the dashboard) can be honest about it.

GDELT and GDACS matching is done by name/ISO code and doesn't have this
limitation.
"""

COUNTRIES = [
    {
        "name": "Turkey",
        "iso2": "TR",
        "iso3": "TUR",
        "gdelt_query": "Turkey",
        "cbs_key": "L008766",
        "cbs_label": "Turkije (TR)",
        "cbs_granularity": "country",
    },
    {
        "name": "Ukraine",
        "iso2": "UA",
        "iso3": "UKR",
        "gdelt_query": "Ukraine",
        "cbs_key": "L009517",
        "cbs_label": "Oost-Europa (region)",
        "cbs_granularity": "region",
    },
    {
        "name": "Lebanon",
        "iso2": "LB",
        "iso3": "LBN",
        "gdelt_query": "Lebanon",
        "cbs_key": "L008524",
        "cbs_label": "Azie (region)",
        "cbs_granularity": "region",
    },
    {
        "name": "Israel",
        "iso2": "IL",
        "iso3": "ISR",
        "gdelt_query": "Israel",
        "cbs_key": "L008524",
        "cbs_label": "Azie (region)",
        "cbs_granularity": "region",
    },
    {
        "name": "Egypt",
        "iso2": "EG",
        "iso3": "EGY",
        "gdelt_query": "Egypt",
        "cbs_key": "L008519",
        "cbs_label": "Afrika (region)",
        "cbs_granularity": "region",
    },
    {
        "name": "Sudan",
        "iso2": "SD",
        "iso3": "SDN",
        "gdelt_query": "Sudan",
        "cbs_key": "L008519",
        "cbs_label": "Afrika (region)",
        "cbs_granularity": "region",
    },
    {
        "name": "Haiti",
        "iso2": "HT",
        "iso3": "HTI",
        "gdelt_query": "Haiti",
        "cbs_key": "L007002",
        "cbs_label": "Midden- en Zuid-Amerika (region)",
        "cbs_granularity": "region",
    },
    {
        "name": "Thailand",
        "iso2": "TH",
        "iso3": "THA",
        "gdelt_query": "Thailand",
        "cbs_key": "L008524",
        "cbs_label": "Azie (region)",
        "cbs_granularity": "region",
    },
]
