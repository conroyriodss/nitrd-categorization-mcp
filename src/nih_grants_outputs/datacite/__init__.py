"""DataCite batch pre-pull support: NIH funder IDs, award matching, REST client.

Used offline by scripts/prepull_datacite.py to build the datacite_outputs table.
The outputs_get_project_datacite tool reads that table; it never calls DataCite.
"""
