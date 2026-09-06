"""Shared seniority vocabulary for multi-board searches.

Single source of truth for the API's search validation (routers/searches.py)
and the scraper's LinkedIn URL builder (scraper/handler.py), so the two
sides can't drift out of sync on valid values or LinkedIn's filter codes.
"""

# Ordered for display in a dropdown, junior → senior.
SENIORITY_LEVELS = ["internship", "entry", "associate", "mid_senior", "director", "executive"]

# LinkedIn Jobs Search "Experience level" filter codes (the f_E query param).
# This is the only one of the multi-board sources with a native, structured
# seniority filter — RemoteOK/WorkingNomads/Remotive/Arbeitnow have no such
# field, so seniority is not applied to them (see handler.py comment).
SENIORITY_TO_LINKEDIN_F_E = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid_senior": "4",
    "director": "5",
    "executive": "6",
}
