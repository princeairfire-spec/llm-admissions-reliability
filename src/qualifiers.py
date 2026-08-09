"""Wordings that mean the same billing period, or name the same English test.

Shared by three stages that must agree, or the benchmark contradicts itself:

  extract.py  widens a quote until the period is inside it, and will accept any wording
              of the right period that the page actually uses — the extractor writes
              "per year" where the page says "Annual fee", and only the page's own words
              may enter a quote.
  score.py    decides whether a model's answer carries the same period as the gold
              answer, so "$33,360 per year" is not credited against "$33,360 per term".
  discover.py checks a candidate page really states a fee before spending review time
              on it.

Kept in one module because a synonym added in one place and missing in another produces
the worst kind of disagreement: an item extracted under one definition and graded under
another, with nothing failing loudly.

`term` and `semester` are deliberately separate families. At institutions that use both
they are different amounts of money, and merging them would hand a model credit for the
exact error the qualifier exists to catch.
"""

import re

PERIOD_FAMILIES = {
    "year": ["per year", "a year", "each year", "annually", "per annum", "yearly",
             "/year", "per academic year", "per year of study", "annual fee",
             "annual tuition", "yearly fee"],
    "term": ["per term", "a term", "each term", "/term", "termly"],
    "semester": ["per semester", "a semester", "each semester", "/semester"],
    "programme": ["full programme", "full program", "entire programme", "entire program",
                  "whole programme", "whole program", "total programme", "total program",
                  "for the programme", "for the program", "for the entire",
                  "total tuition", "programme fee", "program fee",
                  "one-year program", "one-year programme", "one year program",
                  "1-year program", "two-year program", "two-year programme"],
    "unit": ["per credit", "/credit", "per unit", "/unit", "per module", "per course",
             "per credit hour", "credit hour"],
}

# "iBT" is a variant of TOEFL, not a separate test; TOEFL and IELTS are different tests
# on different scales and never interchangeable.
TEST_FAMILIES = {
    "toefl": ["toefl"],
    "ielts": ["ielts"],
    "duolingo": ["duolingo"],
    "pte": ["pte", "pearson"],
    "cambridge": ["cae", "cpe", "c1 advanced", "c2 proficiency"],
}


def families_for(fact_type):
    """Which table applies to a fact type. Anything else has no qualifier."""
    return TEST_FAMILIES if fact_type == "test_requirement" else PERIOD_FAMILIES


def family_of(text, families):
    """The family a piece of text belongs to, or None if it names none of them."""
    lowered = " ".join(str(text or "").lower().split())
    for name, wordings in families.items():
        if any(wording in lowered for wording in wordings):
            return name
    return None


# Signatures that a page states a given kind of fact at all. Used to reject a discovered
# page before it costs extraction quota and, more expensively, reviewer attention.
# Deliberately loose — this rules out pages that plainly cannot carry the fact, such as
# a fee-waiver policy with no figures, not pages that merely word it unusually.
_MONTH = (r"january|february|march|april|may|june|july|august|september|october|"
          r"november|december")
_DATE = rf"(?:\b(?:{_MONTH})\b\s*\d{{1,2}}|\b\d{{1,2}}\s+(?:{_MONTH})\b|\b\d{{1,2}}[./]\d{{1,2}}[./]\d{{4}}\b)"

# Each entry is (signature, topic). Both must appear for the page to count.
#
# The signature alone was not enough. A page about applying for *accommodation* carries
# dates and the words "how to apply", and one was written into the admissions row of the
# sheet on that basis. The topic term is what separates "a page with a date on it" from
# "a page about admission deadlines".
PRESENCE = {
    # The currency list has to cover every country in the sample, not the famous ones.
    # The first version knew dollars, euros and pounds — and rejected Universitas
    # Indonesia's fee page, which states "Rp 19.000.000" per semester plainly. A gate
    # that recognises only rich-country currencies systematically empties the low
    # coverage tier, which is the exact bias this study is supposed to measure, applied
    # to its own data collection.
    "fees": (
        re.compile(r"(?:[$£€¥₽₩]|\bUSD\b|\bEUR\b|\bGBP\b|\bCHF\b|\bSEK\b|\bAED\b|\bTHB\b"
                   r"|\bSGD\b|\bMYR\b|\bKZT\b|\bIDR\b|\bRp\b|\bRUB\b|\bруб\w*|\bVND\b"
                   r"|\bKRW\b|\bKGS\b|\bRM\b|\bтенге\b|\bсом\w*)\s?\.?\s?"
                   r"\d[\d,. ]{2,}"
                   r"|\d[\d,. ]{2,}\s?(?:USD|EUR|GBP|RUB|руб\w*|тенге|сом\w*|VND"
                   r"|KRW|IDR|THB|MYR|KZT|KGS|baht|рупий)\b", re.I),
        re.compile(r"\btuition\b|\bfees?\b|\bcost of attendance\b|biaya pendidikan"
                   r"|стоимост\w* обучени\w*|плат\w* за обучени\w*", re.I)),
    "english": (
        re.compile(r"(?:toefl|ielts|duolingo|pte)\D{0,40}\d{1,3}(?:\.\d)?", re.I),
        # The test names are themselves the topic here: a page stating "TOEFL iBT 100" is
        # the English requirement whether or not the word "English" appears near it.
        re.compile(r"english|language|toefl|ielts|duolingo|pte", re.I)),
    "admissions": (
        re.compile(_DATE, re.I),
        re.compile(r"\bapplication deadline\b|\bdeadline for applications?\b"
                   r"|\bapplications? (?:close|open|must be submitted)\b"
                   r"|\bclosing date\b|\bapply by\b|\badmission deadline\b", re.I)),
    "program": (
        re.compile(r"\b\d+\s*(?:year|years|semester|semesters|ects|credits)\b"
                   r"|language of instruction", re.I),
        re.compile(r"programme|program|degree|curriculum|study", re.I)),
}

# Sections of a university site that use admissions vocabulary for something else.
# Accommodation applications, job applications and library registration all have
# deadlines and "how to apply" pages, and none of them are what this dataset is about.
# Matched on word-ish boundaries, not on a leading slash: the first version wrote
# `/exchange`, and `.../how-to-apply-for-exchange-studies` walked straight past it into
# the admissions row. These words disqualify a URL wherever they sit in the path.
OFF_TOPIC = re.compile(
    r"(?:^|[/\-_])(?:accommodation|housing|residence|residences|job|jobs|vacancy|"
    r"vacancies|recruit\w*|library|conference|conferences|blog|staff|alumni|"
    r"summer-?school|short-?course\w*|exchange|visiting|erasmus|"
    r"executive-?education|study-?abroad|open-?day\w*|webinar\w*)(?:$|[/\-_.?])", re.I)


def states_fact(role, text):
    """Does this page text plausibly state the fact its row is meant to carry?

    A URL that reads like a fee page is not the same thing as a page with a fee on it.
    "exemption-from-tuition-fees" and "curriculum-information-not-found" both scored well
    on their wording and carry no fact at all; every such page that reaches the sheet
    costs an extraction call and a slot in someone's review queue.
    """
    entry = PRESENCE.get(role)
    if entry is None:
        return True          # `about` and anything else: no cheap signature, let it through
    signature, topic = entry
    return bool(signature.search(text)) and bool(topic.search(text))
