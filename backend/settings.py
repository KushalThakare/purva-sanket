"""Configuration shared by the HTTP service and the topic generator."""
import re

PLACEHOLDER_TOPICS = {
    "purva-sanket/REPLACE_WITH_RANDOM_TEAM_ID",
    "purva-sanket/REPLACE_WITH_GENERATED_TOPIC",
    "purva-sanket/YOUR_RANDOM_TEAM_ID",
}


def valid_topic(topic):
    return bool(re.fullmatch(r"purva-sanket/[A-Za-z0-9_-]{8,64}", topic)) and topic not in PLACEHOLDER_TOPICS
