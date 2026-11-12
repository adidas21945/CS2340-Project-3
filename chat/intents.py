"""Story #8: figure out what kind of question someone asked so answer.py cna pick teh right prompt.

We cna make this rules only for it to be instant and free and easy to test, no LLM call needed.
Rules decided by matching, in this order (first one that matches wins):
1. Recovery - if they already paid that matters more than anything else
2. How-to - "how do I report / block / freeze ..."
3. Scam check - "is this a scam?", "a caller says ...", or they pasted the message
4. Factual - "what is a grandparent scam?", "how does it work?"
5. General - nothing else matched so jsut use the base prompt
"""
import re
from enum import Enum


class Intent(str, Enum):
    RECOVERY = "recovery" # already paid, gave info or clicked a link
    HOW_TO = "how_to" # how do i report, block, freeze etc
    SCAM_CHECK = "scam_check" # is this text / call / offer a scam
    FACTUAL = "factual" # what is X, how does X work
    GENERAL = "general" # everything else

    # friendly name we show on teh page, like "Is this a scam?"
    @property
    def label(self) -> str:
        return LABELS[self]


LABELS = {
    Intent.RECOVERY: "What to do after a scam",
    Intent.HOW_TO: "Step-by-step help",
    Intent.SCAM_CHECK: "Is this a scam?",
    Intent.FACTUAL: "Explaining a scam",
    Intent.GENERAL: "General question",
}

# family members since caregivers ask stuff like "my mom sent ..."
_WHO = r"(i|we|my (mom|dad|mother|father|parents?|grandma|grandpa|grandmother|grandfather|husband|wife|aunt|uncle))"
_ACTIONS = r"(report|block|freeze|file|contact|cancel|stop|protect|prevent|avoid|change|reset|place|put|opt|remove|sign up|tell|talk to|help)"


# compile all the patterns once when the file loads so we arent doing it every question
def _compile(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# stuff that for sure means something already happend. ok to check even if they pasted a message
_RECOVERY = _compile(
    r"\balready (paid|sent|wired|gave|replied|clicked|shared|bought|called|transferred)\b",
    r"\b(get|got|getting) (my|our|her|his|their|the) money back\b",
    r"\b(was|were|got|been|being) (scammed|hacked|defrauded|tricked|conned)\b",
    r"\bwhat (do|should|can) (i|we) do now\b",
    r"\bidentity (theft|was stolen)\b",
    r"\blost (\$|money|\d|(my|our|her|his) (savings|money))",
)
# "I sent ...", "my dad gave ...". We skip these on pasted messages bc the scammers own
# text says stuff like "I sent you a package" adn that isnt the user talking
_RECOVERY_FIRST_PERSON = _compile(
    rf"\b{_WHO} (paid|sent|wired|gave|transferred|clicked|bought|shared|downloaded)\b",
)

_HOW_TO = _compile(
    rf"\bhow (do|can|should|would) (i|we|you|someone|my \w+) {_ACTIONS}\b",
    rf"\bhow to {_ACTIONS}\b",
    r"\b(where|who) (do|can|should) (i|we) (report|call|contact|tell|file|go|turn)\b",
    r"\bwhat steps\b",
    r"\b(steps|tips|ways) to (report|protect|avoid|prevent|stop|block)\b",
)

_SCAM_CHECK = _compile(
    r"\b(is|are) (this|that|it|these|they)\b.{0,40}\b(scam|real|legit|legitimate|fake|fraud|safe|phishing)\b",
    r"\b(scam|fake|fraud) or (not|real|legit)\b",
    r"\b(should|can) (i|we) (trust|believe|answer|reply|respond|click|call|pay|open)\b",
    r"\b(got|received|getting|get) (a|an|this|these|some) (\w+ )?(text|email|e-mail|call|message|letter|voicemail|pop-?up|notice|dm)s?\b",
    r"\b(a|the|this) (caller|text|email|message|letter|pop-?up|website|ad|voicemail|recording) (says|said|asks|asked|wants|told|claims|claimed)\b",
    r"\b(someone|somebody|a stranger|a man|a woman|a guy)\b.{0,40}\b(called|texted|emailed|messaged|contacted|says|said|claims|claimed|wants|asked|asks|told)\b",
    r"\b(wants|want|asks|asked|asking|told|telling) (me|us|my \w+) to (pay|send|buy|wire|invest|give|click|call|verify|confirm|download)\b",
    r"\b(needs|wants|asking for|asked for) (money|cash|bail|a loan|gift cards?)\b",
)

_FACTUAL = _compile(
    r"^\s*(what|which|who) (is|are|was|were)\b",
    r"\bwhat'?s (a|an|the)\b",
    r"^\s*(why|how) (do|does|did|would|are|is)\b",
    r"\b(explain|definition|meaning of|tell me about|examples? of|signs of|types of|kinds of)\b",
)

# signs they pasted a text, email or call script instead of asking a question
_URL = re.compile(r"https?://|www\.|\b[\w-]+\.(com|net|org|co|info|xyz|ly)/", re.IGNORECASE)
_PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
_URGENT = re.compile(
    r"\b(urgent|immediately|suspended|verify|final notice|act now|within 24 hours|locked|"
    r"unusual activity|click (here|the link)|congratulations|you have won|winner)\b",
    re.IGNORECASE,
)
PASTED_MIN_CHARS = 120


# true if any pattern in the list shows up anywhere in the text
def _matches(patterns: list[re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in patterns)


# if 2 or more of these show up (long, link, phone number, urgent words, quotes) its probably pasted
def looks_pasted(text: str) -> bool:
    signals = [
        len(text) >= PASTED_MIN_CHARS,
        bool(_URL.search(text)),
        bool(_PHONE.search(text)),
        len(_URGENT.findall(text)) > 0,
        '"' in text or "“" in text or "\n" in text,
    ]
    return sum(signals) >= 2


# go through the rules in order adn return the first intent that matches
# order matters here. recovery is first so "I already paid" never gets treated like a normal
# question, and how-to is before scam check so "how do I report this text" gets steps
def classify_intent(question: str) -> Intent:
    q = question.strip()
    pasted = looks_pasted(q)
    # the first person rules ("I sent") only count if they didnt paste a scammers message
    if _matches(_RECOVERY, q) or (not pasted and _matches(_RECOVERY_FIRST_PERSON, q)):
        return Intent.RECOVERY
    if _matches(_HOW_TO, q):
        return Intent.HOW_TO
    # a pasted message counts as a scam check even if they didnt ask "is this a scam"
    if pasted or _matches(_SCAM_CHECK, q):
        return Intent.SCAM_CHECK
    if _matches(_FACTUAL, q):
        return Intent.FACTUAL
    return Intent.GENERAL
