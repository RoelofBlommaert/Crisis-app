"""
Shared country list for the Crisis & Connectivity Monitor data pulls.

GDELT and GDACS matching is done by name/ISO code. `cbs_rni_name` is the
Dutch country name CBS uses in its "Nederlanders in het buitenland"
maatwerktabel (RNI-derived, see fetch_rni_nederlanders.py) -- CBS uses
Dutch names there ("Turkije", "Oekraïne", ...), not English, so this is
the join key for that source.
"""

COUNTRIES = [
    {
        "name": "Turkey",
        "iso2": "TR",
        "iso3": "TUR",
        "gdelt_query": "Turkey",
        "cbs_rni_name": "Turkije",
    },
    {
        "name": "Ukraine",
        "iso2": "UA",
        "iso3": "UKR",
        "gdelt_query": "Ukraine",
        "cbs_rni_name": "Oekraïne",
    },
    {
        "name": "Lebanon",
        "iso2": "LB",
        "iso3": "LBN",
        "gdelt_query": "Lebanon",
        "cbs_rni_name": "Libanon",
    },
    {
        "name": "Israel",
        "iso2": "IL",
        "iso3": "ISR",
        "gdelt_query": "Israel",
        "cbs_rni_name": "Israël",
    },
    {
        "name": "Egypt",
        "iso2": "EG",
        "iso3": "EGY",
        "gdelt_query": "Egypt",
        "cbs_rni_name": "Egypte",
    },
    {
        "name": "Sudan",
        "iso2": "SD",
        "iso3": "SDN",
        "gdelt_query": "Sudan",
        "cbs_rni_name": "Soedan",
    },
    {
        "name": "Haiti",
        "iso2": "HT",
        "iso3": "HTI",
        "gdelt_query": "Haiti",
        "cbs_rni_name": "Haïti",
    },
    {
        "name": "Thailand",
        "iso2": "TH",
        "iso3": "THA",
        "gdelt_query": "Thailand",
        "cbs_rni_name": "Thailand",
    },
]
