"""NIH Crossref funder IDs used to find NIH-funded DataCite records (hardcoded).

One verified lookup, 2026-10-26T19:19:13Z:
  GET https://api.crossref.org/funders/100000002 -> name + `descendants` (59 IDs),
  then GET https://api.crossref.org/funders/{id} for each ID's name.
  Snapshot: /Volumes/users/conroyri/nitrd_hackathon_v1_raw/datacite/funders/
  crossref_nih_funders_2026-10-26.json (sha256 9494e9b0d6046b6c...).

The IDs are Crossref Funder Registry DOI suffixes (prefix 10.13039). DataCite
stores them in fundingReferences.funderIdentifier, usually as
https://doi.org/10.13039/<id>. They are not re-resolved at runtime. To refresh:
repeat the lookup, diff against these lists and update LOOKUP_DATE.

Queried set (decision 2026-10-26): NIH_FUNDER_IDS = umbrella + 27 current
institutes and centers + 4 legacy IDs = 32. ARPA-H is listed under NIH in
Crossref but is funded separately; it is excluded per funding reference, so a
DOI co-funded by NIH and ARPA-H keeps its NIH attribution. NIH_OTHER_IDS (OD,
programs, divisions) are recorded but not queried unless a harvest shows yield.
"""

from __future__ import annotations

LOOKUP_DATE = "2026-10-26"
CROSSREF_FUNDER_PREFIX = "10.13039/"

NIH_UMBRELLA = {"100000002": "National Institutes of Health"}

# The 27 current institutes and centers (Crossref names; abbreviation comment).
NIH_ICS = {
    "100000054": "National Cancer Institute",  # NCI
    "100000053": "National Eye Institute",  # NEI
    "100000050": "National Heart, Lung, and Blood Institute",  # NHLBI
    "100000051": "National Human Genome Research Institute",  # NHGRI
    "100000049": "National Institute on Aging",  # NIA
    "100000027": "National Institute on Alcohol Abuse and Alcoholism",  # NIAAA
    "100000060": "National Institute of Allergy and Infectious Diseases",  # NIAID
    "100000069": (
        "National Institute of Arthritis and Musculoskeletal and Skin Diseases"
    ),  # NIAMS
    "100000070": "National Institute of Biomedical Imaging and Bioengineering",
    "100009633": (
        "Eunice Kennedy Shriver National Institute of Child Health and Human "
        "Development"
    ),  # NICHD
    "100000055": (
        "National Institute on Deafness and Other Communication Disorders"
    ),  # NIDCD
    "100000072": "National Institute of Dental and Craniofacial Research",
    "100000062": (
        "National Institute of Diabetes and Digestive and Kidney Diseases"
    ),  # NIDDK
    "100000026": "National Institute on Drug Abuse",  # NIDA
    "100000066": "National Institute of Environmental Health Sciences",  # NIEHS
    "100000057": "National Institute of General Medical Sciences",  # NIGMS
    "100000025": "National Institute of Mental Health",  # NIMH
    "100006545": "National Institute on Minority Health and Health Disparities",
    "100000065": "National Institute of Neurological Disorders and Stroke",
    "100000056": "National Institute of Nursing Research",  # NINR
    "100000092": "U.S. National Library of Medicine",  # NLM
    "100006108": "National Center for Advancing Translational Sciences",  # NCATS
    "100008460": "National Center for Complementary and Integrative Health",
    "100000061": "Fogarty International Center",  # FIC
    "100000098": "Clinical Center",  # CC
    "100000093": "Center for Information Technology",  # CIT
    "100005440": "Center for Scientific Review",  # CSR
}

# Older IDs of current ICs; datasets deposited before a rename may carry them.
NIH_LEGACY_IDS = {
    "100000071": "National Institute of Child Health and Human Development",
    "100000096": "National Center on Minority Health and Health Disparities",
    "100000064": "National Center for Complementary and Alternative Medicine",
    "100000097": "National Center for Research Resources",  # NCRR, ended 2011
}

NIH_FUNDER_IDS_CORE = {**NIH_UMBRELLA, **NIH_ICS}
NIH_FUNDER_IDS = {**NIH_FUNDER_IDS_CORE, **NIH_LEGACY_IDS}
"""The 32 IDs that are queried and count as a verified NIH funder."""

# Recorded, NOT queried (Office of the Director, programs, divisions, units).
NIH_OTHER_IDS = {
    "100000052": "NIH Office of the Director",
    "100023790": "Advancing Science and Practice in the Retail Environment",
    "100023885": "All of Us Research Program",
    "100024033": (
        "Artificial Intelligence/Machine Learning Consortium to Advance Health "
        "Equity and Researcher Diversity"
    ),
    "100023835": "BRAIN Initiative",
    "100016229": "Basic Research Laboratory",
    "100015338": "Cancer Moonshot",
    "100020082": "Center for Biomedical Informatics and Information Technology",
    "100031022": "Center for Cancer Research",
    "100023960": "Department of Bioethics",
    "100011541": "Division of Cancer Epidemiology and Genetics",
    "100007316": "Division of Cancer Prevention, National Cancer Institute",
    "100017618": "Division of Diabetes, Endocrinology, and Metabolic Diseases",
    "100006492": "Division of Intramural Research",
    "100017540": "Division of Intramural Research",
    "100012893": "Division of Loan Repayment",
    "100015691": "Division of Microbiology and Infectious Diseases",
    "100030692": "Intramural Research Program",
    "100014124": "Lister Hill National Center for Biomedical Communications",
    "100000135": "NIH Blueprint for Neuroscience Research",
    "100006937": "National Center for Medical Rehabilitation Research",
    "100015615": "National Drug Abuse Treatment Clinical Trials Network",
    "100024032": "Native American Research Centers for Health",
    "100024054": "Network of the National Library of Medicine",
    "100024043": "Pediatric Scientist Development Program",
    "100024042": "Reproductive Scientist Development Program",
    "100016820": "Vaccine Research Center",
}

# Never treated as NIH (separately funded HHS agency listed under NIH).
EXCLUDED_IDS = {"100023015": "Advanced Research Projects Agency for Health (ARPA-H)"}

assert len(NIH_FUNDER_IDS_CORE) == 28
assert len(NIH_FUNDER_IDS) == 32
# Umbrella + Crossref's 59 descendants.
assert len(NIH_FUNDER_IDS) + len(NIH_OTHER_IDS) + len(EXCLUDED_IDS) == 60
assert not set(EXCLUDED_IDS) & set(NIH_FUNDER_IDS)


def normalize_funder_id(value: str | None) -> str | None:
    """Bare Crossref suffix ('100000002') from any common DataCite spelling.

    Accepts https://doi.org/10.13039/<id>, dx.doi.org, 10.13039/<id> or the bare
    digits. Returns None for anything else (ROR, ISNI, free text).
    """
    if not value:
        return None
    text = value.strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    for host in ("dx.doi.org/", "doi.org/"):
        if text.startswith(host):
            text = text[len(host) :]
    if text.startswith(CROSSREF_FUNDER_PREFIX):
        text = text[len(CROSSREF_FUNDER_PREFIX) :]
    return text if text.isdigit() and 6 <= len(text) <= 12 else None
