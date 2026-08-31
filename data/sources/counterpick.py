"""The pages counterpick.gg serves.

Ordinary web pages, fetched with cached_get. Its table is server rendered, so
no browser is needed, and its filters are query parameters.

The project's scope pins two of them: competitive, on console. Region is the
axis we vary, because its figures differ by region and ours should say which
one they came from.
"""

BASE_URL = "https://counterpickgg.com/"
USER_AGENT = "overwatch-db/0.1 (personal project; contact via repo)"

# The sources row this module's pages become.
COUNTERPICK = ("counterpick", "counterpick.gg", "https://counterpickgg.com/")

GAMEMODE = "competitive"
PLATFORM = "console"

# their region values -> the code used in our regions table
# Americas only, to match the rest of the database. The site also publishes
# "all", europe and asia-pacific; they are deliberately not read, because a
# database scoped to one region should not carry rows from another.
REGIONS = {
    "americas": "americas",
}
