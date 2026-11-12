from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from chat.answer import answer_question
from chat.intents import Intent, classify_intent, looks_pasted
from chat.prompts import INTENT_INSTRUCTIONS, NOT_FOUND, build_system_prompt

from .test_views import make_store

# known questions adn the intent each one should get (story #8)
LABELED = [
    # recovery - something already happend
    ("I already paid them with Target gift cards, what now?", Intent.RECOVERY),
    ("I wired money to a scammer yesterday, how do I get it back?", Intent.RECOVERY),
    ("They told me to pay with Target gift cards. What do I do now?", Intent.RECOVERY),
    ("My mom gave her Social Security number to a caller", Intent.RECOVERY),
    ("I think my dad was scammed out of $5,000", Intent.RECOVERY),
    ("I clicked the link in the text and typed my bank password", Intent.RECOVERY),
    # how-to - steps to take
    ("How do I report a scam to the government?", Intent.HOW_TO),
    ("How can I freeze my credit?", Intent.HOW_TO),
    ("How to block robocalls on my phone", Intent.HOW_TO),
    ("Who should I call to report elder fraud?", Intent.HOW_TO),
    # scam check - is this message or offer a scam
    ("Someone called saying they were my grandson in jail and needed bail money. Is that a scam?", Intent.SCAM_CHECK),
    ("A caller says my Medicare card is suspended and asks for my number", Intent.SCAM_CHECK),
    ("A pop-up says my computer has a virus and to call Microsoft", Intent.SCAM_CHECK),
    ("I got a letter saying I won a lottery but need to pay a fee first", Intent.SCAM_CHECK),
    ("Someone I met on Facebook wants me to invest in crypto with guaranteed returns", Intent.SCAM_CHECK),
    ("My online boyfriend needs money for a plane ticket to visit me", Intent.SCAM_CHECK),
    ("Should I call back the number on this voicemail?", Intent.SCAM_CHECK),
    ("Is this gift card request a scam?", Intent.SCAM_CHECK),
    ("USPS: Your package is on hold. Verify your address within 24 hours at http://usps-redelivery.co/track", Intent.SCAM_CHECK),
    # factual - what is it / how does it work
    ("What is a grandparent scam?", Intent.FACTUAL),
    ("How does a tech support scam work?", Intent.FACTUAL),
    ("What are the signs of a romance scam?", Intent.FACTUAL),
    ("Explain phishing", Intent.FACTUAL),
    # general - nothing else matched
    ("Thanks for your help", Intent.GENERAL),
    ("Medicare", Intent.GENERAL),
]

PASTED_TEXT = (
    "Hi Grandma it's me, I sent you this from a friend's phone. I'm in trouble and need $2,000 "
    "for bail immediately. Please don't tell Mom. Call my lawyer at 555-201-3344."
)


# checks the rules put each known question in teh right bucket
class ClassifyIntentTests(SimpleTestCase):
    def test_labeled_questions(self):
        for question, expected in LABELED:
            with self.subTest(question=question):
                self.assertEqual(classify_intent(question), expected)

    def test_pasted_message_is_a_scam_check(self):
        # "I sent you" is the scammer talking not the user so this shouldnt be recovery
        self.assertTrue(looks_pasted(PASTED_TEXT))
        self.assertEqual(classify_intent(PASTED_TEXT), Intent.SCAM_CHECK)

    def test_already_paid_beats_pasted_message(self):
        self.assertEqual(classify_intent(f"I already paid this: {PASTED_TEXT}"), Intent.RECOVERY)

    def test_short_question_is_not_pasted(self):
        self.assertFalse(looks_pasted("Is this a scam?"))


# checks every intent has a prompt adn none of them lose the grounding rules
class SystemPromptTests(SimpleTestCase):
    def test_every_intent_has_instructions(self):
        self.assertEqual(set(INTENT_INSTRUCTIONS), set(Intent))

    def test_every_prompt_keeps_grounding_rules(self):
        # answer.py needs [n] citations adn NOT_FOUND no matter what the intent is
        for intent in Intent:
            with self.subTest(intent=intent):
                prompt = build_system_prompt(intent)
                self.assertIn(NOT_FOUND, prompt)
                self.assertIn("[1]", prompt)
                self.assertIn("ONLY the numbered passages", prompt)

    def test_prompts_differ_by_intent(self):
        self.assertIn("Risk: High", build_system_prompt(Intent.SCAM_CHECK))
        self.assertIn("Do now:", build_system_prompt(Intent.RECOVERY))
        self.assertIn("numbered steps", build_system_prompt(Intent.HOW_TO))
        self.assertNotIn("Risk: High", build_system_prompt(Intent.FACTUAL))


# checks answer.py actually sends the right prompt to the LLM and the page shows the intent
# relevance cutoff is turned off here bc the test store is jsut bag of words, so scores arent real
@override_settings(RELEVANCE_MAX_DISTANCE=1.0)
class IntentWiringTests(TestCase):
    def setUp(self):
        self.store = make_store()

    # ask with a fake LLM reply and give back the answer plus the system prompt it got
    def _ask(self, question):
        with mock.patch("chat.answer.generate", return_value="Gift card payment is a scam [1].") as gen:
            answer = answer_question(question, store=self.store)
        return answer, gen.call_args.args[0] # the system prompt that got sent to the LLM

    def test_recovery_question_uses_recovery_prompt(self):
        answer, system = self._ask("I already paid with a gift card, what now?")
        self.assertEqual(answer.intent, Intent.RECOVERY)
        self.assertEqual(system, build_system_prompt(Intent.RECOVERY))

    def test_scam_check_question_uses_scam_check_prompt(self):
        answer, system = self._ask("They want me to pay with a gift card. Is this a scam?")
        self.assertEqual(answer.intent, Intent.SCAM_CHECK)
        self.assertEqual(system, build_system_prompt(Intent.SCAM_CHECK))

    def test_intent_is_set_when_llm_is_unavailable(self):
        # no key in tests so this falls back to jsut showing the passages
        answer = answer_question("What is a gift card scam?", store=self.store)
        self.assertEqual(answer.intent, Intent.FACTUAL)

    def test_page_shows_detected_intent(self):
        with mock.patch("chat.answer.get_store", return_value=self.store):
            resp = self.client.post(reverse("chat:ask"), {"question": "Is this gift card request a scam?"})
        self.assertContains(resp, "Answering as: Is this a scam?")
