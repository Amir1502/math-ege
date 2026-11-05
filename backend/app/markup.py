import re

MARKUP = re.compile(
    r"<\s*(?:/?[A-Za-z][A-Za-z0-9:._-]*(?=[\s/>])[^>]*|!DOCTYPE\b[^>]*|!--.*?)>",
    re.DOTALL | re.IGNORECASE,
)
