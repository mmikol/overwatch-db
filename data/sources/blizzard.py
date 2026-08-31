"""The pages Blizzard serves.

There is no API here - these are ordinary web pages fetched with cached_get.
The endpoints live in the ingest stage so both Blizzard pipelines name them
once, the way the wiki client does.
"""

BASE_URL = "https://overwatch.blizzard.com/en-us"
HEROES_URL = BASE_URL + "/heroes/"
RATES_URL = BASE_URL + "/rates/"
USER_AGENT = "overwatch-db/0.1 (personal project; contact via repo)"

# The sources row this module's pages become.
BLIZZARD = ("blizzard", "Blizzard Overwatch site", "https://overwatch.blizzard.com/en-us/")
