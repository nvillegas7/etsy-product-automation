"""Story engine: parameterized, hand-written story arcs for picture books.

Each moral has two distinct scenario skeletons (e.g. sharing: "the kite" /
"the berry basket").  A story is a sequence of *beats* -- intro, daily joy,
a problem tied to the moral, a wrong choice or struggle, its consequence,
gentle guidance from a mentor, making it right, celebration, and a lesson
recap.  Every beat carries hand-written sentence variants per age band and
per narrative style (prose or rhyming AABB couplets with fixed rhyme words
so the rhymes always land).

The same seed always produces the same story.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Story dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoryPage:
    """One story spread: the text plus visual hints for the illustrator."""

    text: str
    beat: str
    expression: str = "happy"
    pose: str = "stand"
    friend_expression: str = "happy"
    show_friend: bool = False
    show_mentor: bool = False
    composition: str = "center"       # left | right | center | closeup
    time_of_day: str = "day"          # day | morning | overcast | sunset | night
    shot: str = "wide"                # establish | wide | corner | path | close | hill
    zone: str = ""                    # sub-location of the setting (see scenes.py)


@dataclass(frozen=True)
class Story:
    """A fully-assembled story ready for illustration."""

    title: str
    subtitle: str
    pages: list[StoryPage]
    lesson_heading: str
    lesson_text: str
    character_key: str
    character_name: str               # e.g. "Penny"
    character_full_name: str          # e.g. "Penny the Pear"
    friend_key: str
    friend_name: str                  # e.g. "Felix"
    mentor_key: str                   # owl | bee | turtle
    mentor_name: str                  # e.g. "Grandma Owl"
    setting: str
    moral: str
    scenario_id: str = ""
    context: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Setting flavor
# ---------------------------------------------------------------------------

SETTING_PHRASES: dict[str, dict[str, str]] = {
    "park":   {"place": "the sunny park", "feature": "the old oak tree",
               "activity": "play on the swings"},
    "forest": {"place": "the whispering forest", "feature": "the mossy log",
               "activity": "play hide-and-seek"},
    "zoo":    {"place": "the friendly zoo", "feature": "the big zoo gate",
               "activity": "visit all the animals"},
    "city":   {"place": "the busy little city", "feature": "the corner lamppost",
               "activity": "splash in fountain puddles"},
    "farm":   {"place": "the rolling green farm", "feature": "the big red barn",
               "activity": "tumble in the hay"},
    "beach":  {"place": "the golden beach", "feature": "the tall lighthouse rock",
               "activity": "build sandcastles"},
    "school": {"place": "the little schoolhouse yard", "feature": "the painted hopscotch square",
               "activity": "play at recess"},
    "garden": {"place": "the blooming garden", "feature": "the crooked picket fence",
               "activity": "smell the roses"},
}

# Mentor rotation per setting -- a small pool of wise, mentor-suitable
# critters.  One is chosen deterministically per book (by seed); conflicts
# (mentor species == a cast member) fall through to the next available.
SETTING_MENTOR_POOLS: dict[str, tuple[str, ...]] = {
    "park":   ("owl", "squirrel", "ladybug"),
    "forest": ("owl", "squirrel"),
    "zoo":    ("owl", "ladybug"),
    "city":   ("owl", "ladybug"),
    "garden": ("bee", "ladybug", "snail"),
    "farm":   ("bee", "owl", "ladybug"),
    "school": ("bee", "owl", "ladybug"),
    "beach":  ("turtle", "owl"),
}
# Global fall-through order when a whole pool clashes with the cast.
MENTOR_FALLBACK: tuple[str, ...] = ("owl", "bee", "turtle", "squirrel", "ladybug", "snail")
MENTOR_NAMES: dict[str, str] = {
    "owl": "Grandma Owl",
    "bee": "Buzz the Bee",
    "turtle": "Old Sage the Turtle",
    "squirrel": "Nutmeg the Squirrel",
    "ladybug": "Dot the Ladybug",
    "snail": "Pokey the Snail",
}
MENTOR_SHORT: dict[str, str] = {
    "owl": "Grandma Owl",
    "bee": "Buzz",
    "turtle": "Old Sage",
    "squirrel": "Nutmeg",
    "ladybug": "Dot",
    "snail": "Pokey",
}


# ---------------------------------------------------------------------------
# Generic beats (prose): tuples of sentences.
# Age bands consume a prefix: 2-4 -> first sentence, 4-6 -> two, 6-8 -> all.
# The first sentence of every tuple is 8 words or fewer.
# ---------------------------------------------------------------------------

GENERIC_PROSE: dict[str, tuple[str, ...]] = {
    "intro": (
        "This is {short} the {species}.",
        "{short} lived in {place}.",
        "Just past {feature}, {short}'s little home was always warm and snug.",
    ),
    "joy": (
        "{short} loved to {activity}.",
        "Every day was full of games and giggles.",
        "Even the sun seemed to peek down and smile at the fun.",
    ),
    "friend": (
        "{friend_short} the {friend_species} came to play.",
        "“Hello, {short}!” called {friend_short} with a wave.",
        "The two friends did everything together, side by side.",
    ),
    "activity": (
        "Together they liked to {activity}.",
        "They laughed until their tummies wobbled.",
        "Best friends make even little games feel like grand adventures.",
    ),
    "mentor": (
        "Then {mentor_short} came along.",
        "{mentor_short} had kind eyes and a gentle voice.",
        "“Something seems heavy in your heart, little one,” said {mentor_short} softly.",
    ),
    "feelings": (
        "{short} felt sad inside.",
        "{short}'s tummy wobbled and the smiles ran away.",
        "Being {wrong_feeling} had not felt good at all — not even a little.",
    ),
    "decision": (
        "{short} took a big, brave breath.",
        "Now {short} knew just what to do.",
        "A warm little spark of {moral} glowed inside {short}'s heart.",
    ),
    "reaction": (
        "{friend_short} smiled a great big smile.",
        "“Thank you, {short}!” {friend_short} cheered.",
        "Warm, fuzzy feelings filled {place} from end to end.",
    ),
    "celebration": (
        "The friends played until the sky turned pink.",
        "There were giggles and happy dances all around.",
        "It was the very best day {place} had ever seen.",
    ),
}

# Generic beats (rhyme): AABB couplets with fixed rhyme words.
GENERIC_RHYME: dict[str, str] = {
    "intro": "In {place} where the soft winds play,\nlived {short} the {species}, who smiled all day.",
    "joy": "Each morning brought a brand-new game,\nno two giggles were quite the same.",
    "friend": "Along came {friend_short}, with a wave and a grin:\n“Hello, good friend! May I join in?”",
    "activity": "They hopped and they skipped, they twirled around,\nthe happiest pair that could be found.",
    "mentor": "Then kind old {mentor_short} came wandering near:\n“Tell me your trouble, my little dear.”",
    "feelings": "A wibbly-wobbly feeling grew,\nand {short} felt sorry through and through.",
    "decision": "{short} took a breath and stood up tall:\n“I can make this right, once and for all!”",
    "reaction": "{friend_short} beamed a smile so wide and bright,\nthe whole of {place} felt warm with light.",
    "celebration": "They laughed and they played till the sun went to bed,\nwith joy in each heart and each sleepy head.",
}


# ---------------------------------------------------------------------------
# Moral scenarios: two skeletons per moral.
# Each scenario: id, slot words, and prose sentence-tuples for the seven
# moral-specific beats.
# ---------------------------------------------------------------------------

MORAL_SCENARIOS: dict[str, list[dict]] = {
    # ------------------------------------------------------------- sharing
    "sharing": [
        {
            "id": "kite",
            "thing": "shiny red kite",
            "thing_short": "kite",
            "wrong_feeling": "selfish",
            "prose": {
                "problem_setup": (
                    "{short} had a shiny new {thing_short}.",
                    "“May I have a turn, please?” {friend_short} asked.",
                    "The {thing_short} bobbed in the breeze, ready for more fun.",
                ),
                "problem_grows": (
                    "{short} held the {thing_short} tight.",
                    "What if {friend_short} kept it forever?",
                    "A prickly, worried feeling crept in like a cloud across the sun.",
                ),
                "wrong_choice": (
                    "“No! It is mine!” said {short}.",
                    "{short} turned away and hid the {thing_short}.",
                    "{friend_short}'s happy face slowly folded into a frown.",
                ),
                "consequence": (
                    "{friend_short} walked away, very sad.",
                    "Now the game was quiet and lonely.",
                    "The {thing_short} did not feel so wonderful anymore.",
                ),
                "guidance": (
                    "“Toys are sweeter shared,” said {mentor_short}.",
                    "“Fun grows bigger when you give some away.”",
                    "“A turn for a friend is a gift that comes right back.”",
                ),
                "making_right": (
                    "{short} ran to find {friend_short}.",
                    "“Here — you take a turn first!”",
                    "Together they watched the {thing_short} dance high above {place}.",
                ),
                "lesson": (
                    "Sharing made the fun grow bigger.",
                    "From that day on, {short} always shared.",
                    "Because everything lovely is twice as lovely when it is shared.",
                ),
            },
        },
        {
            "id": "berries",
            "thing": "basket of sweet berries",
            "thing_short": "berries",
            "wrong_feeling": "selfish",
            "prose": {
                "problem_setup": (
                    "{short} found a basket of berries.",
                    "They smelled as sweet as summer jam.",
                    "{friend_short} peeked over, hoping for a taste.",
                ),
                "problem_grows": (
                    "There were only a few berries left.",
                    "{short} counted them one by one.",
                    "Sharing them suddenly felt very, very hard.",
                ),
                "wrong_choice": (
                    "{short} hid the basket behind a bush.",
                    "“All mine,” {short} whispered.",
                    "But the berries tasted strangely plain, eaten all alone.",
                ),
                "consequence": (
                    "{friend_short} went home with an empty tummy.",
                    "The afternoon felt long and quiet.",
                    "Even the sweetest berry could not fix the lonely feeling.",
                ),
                "guidance": (
                    "“Sweet things love company,” said {mentor_short}.",
                    "“A treat shared with a friend tastes twice as sweet.”",
                    "“Full tummies are good, but full hearts are better.”",
                ),
                "making_right": (
                    "{short} carried the basket to {friend_short}.",
                    "“The biggest one is for you!”",
                    "They munched and giggled until every berry was gone.",
                ),
                "lesson": (
                    "Shared berries really were sweeter.",
                    "{short} never hid a treat again.",
                    "For a treat that is shared feeds two hearts at once.",
                ),
            },
        },
    ],
    # ------------------------------------------------------------ kindness
    "kindness": [
        {
            "id": "tumble",
            "thing": "big game of tag",
            "thing_short": "game",
            "wrong_feeling": "unkind",
            "prose": {
                "problem_setup": (
                    "{friend_short} tripped and tumbled down.",
                    "Bump! Right onto the ground.",
                    "{friend_short}'s eyes went shiny with little tears.",
                ),
                "problem_grows": (
                    "Everyone kept playing the {thing_short}.",
                    "Nobody stopped to help.",
                    "{friend_short} sat all alone, rubbing a sore knee.",
                ),
                "wrong_choice": (
                    "{short} ran right past.",
                    "“No time! I am winning!” called {short}.",
                    "The {thing_short} suddenly seemed more important than a friend.",
                ),
                "consequence": (
                    "But winning felt strangely empty.",
                    "{short} looked back at {friend_short}, all alone.",
                    "A win without kindness is a very small win indeed.",
                ),
                "guidance": (
                    "“Kind hearts stop to help,” said {mentor_short}.",
                    "“A friend matters more than any game.”",
                    "“One small kindness can dry a whole puddle of tears.”",
                ),
                "making_right": (
                    "{short} hurried back to {friend_short}.",
                    "“Are you okay? Lean on me.”",
                    "{short} helped {friend_short} up, gentle as can be.",
                ),
                "lesson": (
                    "Helping felt better than winning.",
                    "{short} chose kindness from then on.",
                    "For a kind heart wins the best prize of all — a friend.",
                ),
            },
        },
        {
            "id": "newcomer",
            "thing": "brand-new neighbor",
            "thing_short": "new friend",
            "wrong_feeling": "unkind",
            "prose": {
                "problem_setup": (
                    "Someone new stood by {feature}.",
                    "The little newcomer looked shy and small.",
                    "Nobody said hello, and nobody asked them to play.",
                ),
                "problem_grows": (
                    "The newcomer watched the games alone.",
                    "{short} felt a tug inside.",
                    "But going first felt scary, like jumping into cold water.",
                ),
                "wrong_choice": (
                    "{short} looked away and kept playing.",
                    "“Someone else will say hi,” thought {short}.",
                    "But no one did, and the newcomer's head drooped low.",
                ),
                "consequence": (
                    "The newcomer sat alone all afternoon.",
                    "{short}'s game stopped feeling fun.",
                    "It is hard to laugh while someone nearby feels forgotten.",
                ),
                "guidance": (
                    "“Kindness goes first,” said {mentor_short}.",
                    "“A hello is a tiny gift anyone can give.”",
                    "“The bravest, kindest word in the world is ‘welcome.’”",
                ),
                "making_right": (
                    "{short} walked over and smiled.",
                    "“Hello! Want to play with us?”",
                    "The newcomer's face lit up like a little sunrise.",
                ),
                "lesson": (
                    "One hello made a new friend.",
                    "{short} learned that kindness goes first.",
                    "Because a welcome, warmly given, can brighten a whole world.",
                ),
            },
        },
    ],
    # ------------------------------------------------------------- honesty
    "honesty": [
        {
            "id": "flowerpot",
            "thing": "pretty flower pot",
            "thing_short": "flower pot",
            "wrong_feeling": "untruthful",
            "prose": {
                "problem_setup": (
                    "Crash! The {thing_short} tipped over.",
                    "{short} had bumped it while playing.",
                    "Bits and petals lay scattered across the ground.",
                ),
                "problem_grows": (
                    "Footsteps! Someone was coming.",
                    "{short}'s heart went thump, thump, thump.",
                    "Telling the truth suddenly felt as big as a mountain.",
                ),
                "wrong_choice": (
                    "“The wind did it!” said {short}.",
                    "The fib slipped out fast and easy.",
                    "But it sat in {short}'s tummy like a heavy stone.",
                ),
                "consequence": (
                    "The fib grew heavier all day.",
                    "{short} could not enjoy a single game.",
                    "A hidden truth has a way of squeezing all the fun out.",
                ),
                "guidance": (
                    "“Truth is lighter than a fib,” said {mentor_short}.",
                    "“Brave hearts say what really happened.”",
                    "“A mistake plus the truth can always be mended.”",
                ),
                "making_right": (
                    "“It was me. I am sorry,” said {short}.",
                    "The heavy stone melted right away.",
                    "Together they planted the flowers again, better than before.",
                ),
                "lesson": (
                    "The truth made {short} feel light.",
                    "{short} promised to always be honest.",
                    "For the truth, though it wobbles, always stands up straight.",
                ),
            },
        },
        {
            "id": "cookie",
            "thing": "last honey cookie",
            "thing_short": "cookie",
            "wrong_feeling": "untruthful",
            "prose": {
                "problem_setup": (
                    "One {thing_short} sat on the plate.",
                    "It was saved for everyone to split.",
                    "{short}'s tummy rumbled a hungry little song — and the {thing_short} vanished.",
                ),
                "problem_grows": (
                    "“Who ate the {thing_short}?” asked {friend_short}.",
                    "{short}'s cheeks went warm and pink.",
                    "The empty plate seemed to stare right up at {short}.",
                ),
                "wrong_choice": (
                    "“Not me!” said {short} quickly.",
                    "The fib hopped out before {short} could stop it.",
                    "But crumbs clung to {short}'s chin and told a different story.",
                ),
                "consequence": (
                    "{friend_short} looked at {short} sadly.",
                    "“I just wish you had told me.”",
                    "The sweet taste turned sour with the secret.",
                ),
                "guidance": (
                    "“Little fibs grow big,” said {mentor_short}.",
                    "“Honesty keeps friendships strong and sweet.”",
                    "“Owning up is the fastest way back to a happy heart.”",
                ),
                "making_right": (
                    "“I ate it. I am sorry,” said {short}.",
                    "“Thank you for telling the truth,” said {friend_short}.",
                    "Together they baked a whole new batch to share.",
                ),
                "lesson": (
                    "The truth tasted better than cookies.",
                    "{short} never fibbed again.",
                    "Because honesty is the sweetest recipe of all.",
                ),
            },
        },
    ],
    # ------------------------------------------------------------ patience
    "patience": [
        {
            "id": "seed",
            "thing": "little seed",
            "thing_short": "seed",
            "wrong_feeling": "impatient",
            "prose": {
                "problem_setup": (
                    "{short} planted a little seed.",
                    "“Grow!” said {short}. “Grow right now!”",
                    "But the seed just sat quietly under its blanket of soil.",
                ),
                "problem_grows": (
                    "A day passed. Then another.",
                    "Still no sprout, not even a tiny one.",
                    "Waiting felt like the slowest thing in the whole world.",
                ),
                "wrong_choice": (
                    "{short} dug the seed back up.",
                    "“Why are you so slow?”",
                    "The poor seed lay blinking in the sudden sunshine.",
                ),
                "consequence": (
                    "Dug-up seeds cannot grow at all.",
                    "{short} sighed a great big sigh.",
                    "Rushing had only made the waiting start all over again.",
                ),
                "guidance": (
                    "“Good things grow slowly,” said {mentor_short}.",
                    "“Water, wait, and trust — that is the secret.”",
                    "“Patience is a quiet kind of magic.”",
                ),
                "making_right": (
                    "{short} tucked the seed back in.",
                    "Each day: water, wait, and a kind word.",
                    "{short} sang to it softly and did not peek even once.",
                ),
                "lesson": (
                    "One morning — a tiny green sprout!",
                    "Waiting had worked its quiet magic.",
                    "For the sweetest things always take their own sweet time.",
                ),
            },
        },
        {
            "id": "swing",
            "thing": "big rope swing",
            "thing_short": "swing",
            "wrong_feeling": "impatient",
            "prose": {
                "problem_setup": (
                    "Everyone wanted a turn on the {thing_short}.",
                    "The line was long, long, long.",
                    "{short} hopped from foot to foot, waiting.",
                ),
                "problem_grows": (
                    "The line moved slower than a snail.",
                    "{short}'s patience shrank smaller and smaller.",
                    "“I cannot wait one more minute!” {short} huffed.",
                ),
                "wrong_choice": (
                    "{short} pushed right to the front.",
                    "“Me first!”",
                    "Behind {short}, poor {friend_short} stumbled and nearly fell.",
                ),
                "consequence": (
                    "The fun fizzled right away.",
                    "Everyone looked upset — even the {thing_short} seemed droopy.",
                    "A turn taken too soon never feels quite right.",
                ),
                "guidance": (
                    "“Turns come to those who wait,” said {mentor_short}.",
                    "“Waiting well is its own little victory.”",
                    "“And while you wait, you can cheer for your friends.”",
                ),
                "making_right": (
                    "{short} went to the very back.",
                    "“Sorry, everyone. Your turns first!”",
                    "{short} clapped and cheered for every single swing.",
                ),
                "lesson": (
                    "At last, {short}'s turn came!",
                    "And it was worth every minute.",
                    "For a turn that is waited for swings the very highest.",
                ),
            },
        },
    ],
    # ------------------------------------------------------------- courage
    "courage": [
        {
            "id": "bridge",
            "thing": "wobbly little bridge",
            "thing_short": "bridge",
            "wrong_feeling": "discouraged",
            "prose": {
                "problem_setup": (
                    "A {thing_short} stood in the way.",
                    "It creaked and swayed in the wind.",
                    "On the other side, the friends were waiting.",
                ),
                "problem_grows": (
                    "{short}'s knees began to wobble too.",
                    "The {thing_short} looked longer every second.",
                    "Fear whispered, “You are much too small for this.”",
                ),
                "wrong_choice": (
                    "{short} turned and hid.",
                    "“I cannot do it,” {short} whispered.",
                    "Hiding felt safe, but it also felt very small.",
                ),
                "consequence": (
                    "The fun carried on far away.",
                    "{short} watched from behind {feature}.",
                    "Missing out felt even worse than being scared.",
                ),
                "guidance": (
                    "“Brave means scared plus one step,” said {mentor_short}.",
                    "“Courage is not big. It is one little step, then another.”",
                    "“Take a deep breath, and take just one step.”",
                ),
                "making_right": (
                    "{short} took one step. Then another.",
                    "The {thing_short} creaked — and held!",
                    "Step by wobbly step, {short} crossed to the cheering friends.",
                ),
                "lesson": (
                    "{short} had been brave after all.",
                    "The fear got smaller with every step.",
                    "For courage grows each time you use it, step by little step.",
                ),
            },
        },
        {
            "id": "hollow",
            "thing": "deep dark hollow",
            "thing_short": "hollow",
            "wrong_feeling": "discouraged",
            "prose": {
                "problem_setup": (
                    "{friend_short}'s ball rolled into the {thing_short}.",
                    "Inside, it was dark as nighttime.",
                    "“Will you help me?” asked {friend_short} in a small voice.",
                ),
                "problem_grows": (
                    "{short} peeked into the dark.",
                    "Shapes and shadows seemed to wiggle.",
                    "{short}'s heart drummed a fast little drum.",
                ),
                "wrong_choice": (
                    "“I am too scared,” said {short}.",
                    "{short} backed away from the {thing_short}.",
                    "{friend_short}'s shoulders drooped all the way down.",
                ),
                "consequence": (
                    "The ball stayed lost in the dark.",
                    "{friend_short} sniffled quietly.",
                    "And the fear only grew bigger the longer {short} fed it.",
                ),
                "guidance": (
                    "“Shadows are smaller than they look,” said {mentor_short}.",
                    "“Hold a friend's hand and look again.”",
                    "“Brave hearts shine brightest in dark places.”",
                ),
                "making_right": (
                    "{short} held {friend_short}'s hand tight.",
                    "One breath. One step. Into the dark.",
                    "And there was the ball — plus nothing scary at all!",
                ),
                "lesson": (
                    "The dark was not so big.",
                    "{short}'s courage had lit the way.",
                    "For bravery is a little lantern that grows as you go.",
                ),
            },
        },
    ],
    # ----------------------------------------------------------- obedience
    "obedience": [
        {
            "id": "gate",
            "thing": "garden gate",
            "thing_short": "gate",
            "wrong_feeling": "sorry for not listening",
            "prose": {
                "problem_setup": (
                    "“Stay inside the {thing_short},” said {mentor_short}.",
                    "“I will be back very soon.”",
                    "{short} nodded — but the world outside looked shiny.",
                ),
                "problem_grows": (
                    "Something fluttered past the {thing_short}.",
                    "A butterfly! A beautiful one!",
                    "“Just one tiny peek,” thought {short}.",
                ),
                "wrong_choice": (
                    "{short} slipped through the {thing_short}.",
                    "One hop, two hops, three hops — gone!",
                    "Soon nothing around looked familiar at all.",
                ),
                "consequence": (
                    "{short} was lost and alone.",
                    "Every path looked wiggly and wrong.",
                    "“I wish I had listened,” {short} whispered.",
                ),
                "guidance": (
                    "{mentor_short} found {short} at last.",
                    "“Rules are hugs made of words. They keep you safe.”",
                    "“I ask because I love you, little one.”",
                ),
                "making_right": (
                    "“I am sorry. I will listen,” said {short}.",
                    "Hand in hand, they walked safely home.",
                    "The {thing_short} clicked shut like a goodnight kiss.",
                ),
                "lesson": (
                    "Listening kept {short} safe and snug.",
                    "{short} always listened after that.",
                    "For little ears that listen keep little hearts safe.",
                ),
            },
        },
        {
            "id": "bedtime",
            "thing": "bedtime bell",
            "thing_short": "bell",
            "wrong_feeling": "sorry for not listening",
            "prose": {
                "problem_setup": (
                    "Ding! The {thing_short} rang softly.",
                    "“Time to rest,” called {mentor_short}.",
                    "But {short} was right in the middle of a game.",
                ),
                "problem_grows": (
                    "“Five more minutes,” said {short}.",
                    "Then five became ten, then more.",
                    "The stars came out to watch, one sleepy eye at a time.",
                ),
                "wrong_choice": (
                    "{short} played on and on.",
                    "“Rest is for babies!” {short} giggled.",
                    "High above, the moon shook its round silver head.",
                ),
                "consequence": (
                    "The next day, {short} was so tired.",
                    "Too tired to play. Too tired to smile.",
                    "Everything fun felt heavy and slow.",
                ),
                "guidance": (
                    "“Rest makes room for fun,” said {mentor_short}.",
                    "“When I call you in, I am caring for you.”",
                    "“Tomorrow's games need tonight's sleep.”",
                ),
                "making_right": (
                    "That night, the {thing_short} rang once.",
                    "{short} hopped straight into bed.",
                    "“Goodnight!” {short} yawned, and dreamed the sweetest dreams.",
                ),
                "lesson": (
                    "{short} woke up bright and bouncy.",
                    "Listening had filled the whole day with sunshine.",
                    "For sleep that comes when called brings mornings full of play.",
                ),
            },
        },
    ],
    # ---------------------------------------------------------- politeness
    "politeness": [
        {
            "id": "picnic",
            "thing": "picnic treats",
            "thing_short": "treats",
            "wrong_feeling": "rude",
            "prose": {
                "problem_setup": (
                    "A picnic! With yummy treats!",
                    "Everyone gathered around the blanket.",
                    "{short}'s eyes grew as wide as saucers.",
                ),
                "problem_grows": (
                    "{short} wanted the biggest treat.",
                    "Wanting it NOW made {short}'s tummy do flips.",
                    "Magic words? {short} forgot all about them.",
                ),
                "wrong_choice": (
                    "“Gimme that!” {short} grabbed.",
                    "No please. No thank you. Just grab!",
                    "The picnic went quiet as a held breath.",
                ),
                "consequence": (
                    "Nobody wanted to sit by {short}.",
                    "Rude little grabs make lonely little friends.",
                    "The treat tasted fine, but the day felt spoiled.",
                ),
                "guidance": (
                    "“Try the magic words,” said {mentor_short}.",
                    "“‘Please’ opens doors. ‘Thank you’ keeps them open.”",
                    "“Gentle words make everything taste sweeter.”",
                ),
                "making_right": (
                    "“May I please have one?” asked {short}.",
                    "“Of course!” everyone said at once.",
                    "“Thank you!” beamed {short} — and the picnic bloomed again.",
                ),
                "lesson": (
                    "The magic words really were magic.",
                    "{short} used them every single day.",
                    "For ‘please’ and ‘thank you’ are tiny keys to happy hearts.",
                ),
            },
        },
        {
            "id": "storytime",
            "thing": "story circle",
            "thing_short": "story",
            "wrong_feeling": "rude",
            "prose": {
                "problem_setup": (
                    "Story time by {feature}!",
                    "{mentor_short} began a wonderful story.",
                    "Everyone leaned in close to listen.",
                ),
                "problem_grows": (
                    "{short} thought of something exciting.",
                    "It bubbled and fizzed inside.",
                    "Waiting to speak felt like holding in a sneeze.",
                ),
                "wrong_choice": (
                    "“ME! LISTEN TO ME!” shouted {short}.",
                    "The story screeched to a stop.",
                    "Everyone's ears drooped at the loud, loud noise.",
                ),
                "consequence": (
                    "The story lost its sparkle.",
                    "Friends turned away, just a little.",
                    "Loud words had squashed the cozy listening quiet.",
                ),
                "guidance": (
                    "“Ears first, words second,” said {mentor_short}.",
                    "“Everyone gets a turn to talk.”",
                    "“Waiting your turn shows friends you care.”",
                ),
                "making_right": (
                    "{short} sat quietly and listened.",
                    "When the story ended, {short} raised a hand.",
                    "“Excuse me — may I share now?” And everyone smiled yes.",
                ),
                "lesson": (
                    "Listening made {short}'s words sweeter.",
                    "Now {short} waits, then speaks kindly.",
                    "For polite little voices are the easiest ones to love.",
                ),
            },
        },
    ],
    # ----------------------------------------------------------- gratitude
    "gratitude": [
        {
            "id": "scarf",
            "thing": "little knitted scarf",
            "thing_short": "scarf",
            "wrong_feeling": "ungrateful",
            "prose": {
                "problem_setup": (
                    "{friend_short} brought {short} a gift.",
                    "A small, soft, slightly wiggly scarf.",
                    "{friend_short} had made it all alone, stitch by stitch.",
                ),
                "problem_grows": (
                    "{short} had wished for something big.",
                    "Something shiny! Something grand!",
                    "The little {thing_short} looked plain beside that big wish.",
                ),
                "wrong_choice": (
                    "“Is that all?” sighed {short}.",
                    "No thank you. Not even a smile.",
                    "{friend_short} hugged the {thing_short} and looked at the ground.",
                ),
                "consequence": (
                    "{friend_short} left without a word.",
                    "The {thing_short} lay where it fell.",
                    "Somehow the whole day felt colder after that.",
                ),
                "guidance": (
                    "“Count the love, not the size,” said {mentor_short}.",
                    "“A grateful heart sees treasure everywhere.”",
                    "“Every gift carries a piece of someone's heart.”",
                ),
                "making_right": (
                    "{short} wrapped up in the {thing_short}.",
                    "It was warm — warm as a hug.",
                    "“Thank you, {friend_short}. I love it. Truly!”",
                ),
                "lesson": (
                    "Thank-yous made everything feel bigger.",
                    "{short} said thank you every day.",
                    "For grateful eyes find gold in the littlest things.",
                ),
            },
        },
        {
            "id": "rainyday",
            "thing": "rainy gray morning",
            "thing_short": "rain",
            "wrong_feeling": "grumbly",
            "prose": {
                "problem_setup": (
                    "Drip, drop — rain everywhere!",
                    "No games outside today.",
                    "{short} pressed a sad face against the window.",
                ),
                "problem_grows": (
                    "“This day is ruined!” grumbled {short}.",
                    "Grumble, grumble, all morning long.",
                    "Every little thing seemed wrong, plain, and boring.",
                ),
                "wrong_choice": (
                    "{short} stomped and pouted.",
                    "“Nothing good ever happens to me!”",
                    "The grumbles piled up like soggy socks.",
                ),
                "consequence": (
                    "The grumbling made everything worse.",
                    "Even warm cocoa tasted grumbly.",
                    "A grumpy heart cannot taste the sweet parts of a day.",
                ),
                "guidance": (
                    "“Look for the little gifts,” said {mentor_short}.",
                    "“Warm homes. Good friends. Cozy sounds.”",
                    "“Thankful eyes turn gray days golden.”",
                ),
                "making_right": (
                    "{short} looked again, slowly.",
                    "Pitter-patter music! Puddle mirrors! Cozy blankets!",
                    "“Thank you, little rain,” whispered {short} — and meant it.",
                ),
                "lesson": (
                    "The gray day sparkled after all.",
                    "{short} found gifts hiding everywhere.",
                    "For a thankful heart makes every day a present.",
                ),
            },
        },
    ],
    # ------------------------------------------------------------ teamwork
    "teamwork": [
        {
            "id": "pumpkin",
            "thing": "great big pumpkin",
            "thing_short": "pumpkin",
            "wrong_feeling": "stubborn",
            "prose": {
                "problem_setup": (
                    "A great big pumpkin needed moving!",
                    "It was round and grand and HEAVY.",
                    "It had to get all the way across {place}.",
                ),
                "problem_grows": (
                    "{short} pushed. And pushed.",
                    "The {thing_short} rolled back every time.",
                    "“I can do it all by myself!” puffed {short}.",
                ),
                "wrong_choice": (
                    "“No help needed!” said {short}.",
                    "Push, wobble, roll... squash-bump!",
                    "Down sat {short}, out of puff, with the pumpkin unmoved.",
                ),
                "consequence": (
                    "The {thing_short} had not moved a whisker.",
                    "{short} was tired from top to toes.",
                    "Some jobs are simply too big for one.",
                ),
                "guidance": (
                    "“Many hands make light work,” said {mentor_short}.",
                    "“Asking for help is a strength, not a stumble.”",
                    "“Together, friends can move mountains — and pumpkins.”",
                ),
                "making_right": (
                    "“Friends! Will you help me?” called {short}.",
                    "Everyone pushed together — one, two, THREE!",
                    "The {thing_short} rolled along as easy as a giggle.",
                ),
                "lesson": (
                    "Together, the big job felt small.",
                    "{short} learned to say ‘let's do it together.’",
                    "For teamwork turns impossible into easy-peasy.",
                ),
            },
        },
        {
            "id": "parade",
            "thing": "grand parade",
            "thing_short": "parade",
            "wrong_feeling": "bossy",
            "prose": {
                "problem_setup": (
                    "The friends planned a grand parade!",
                    "Music, flags, and fancy marching.",
                    "Everyone had a special part to play.",
                ),
                "problem_grows": (
                    "{short} wanted every part.",
                    "The flag! The drum! The lead!",
                    "“I can do it best,” declared {short}.",
                ),
                "wrong_choice": (
                    "{short} took all the jobs.",
                    "Drum, flag, march — all at once!",
                    "Bang-crash-tangle! The {thing_short} wobbled to a stop.",
                ),
                "consequence": (
                    "The {thing_short} fell all to pieces.",
                    "The friends stood empty-handed and glum.",
                    "One busy star cannot shine like a whole sky.",
                ),
                "guidance": (
                    "“A team shines together,” said {mentor_short}.",
                    "“Every friend needs a part to play.”",
                    "“The best music comes when everyone plays along.”",
                ),
                "making_right": (
                    "{short} handed out the jobs.",
                    "A drum for you! A flag for you!",
                    "The {thing_short} marched through {place}, splendid at last.",
                ),
                "lesson": (
                    "Sharing the jobs made magic.",
                    "{short} loved being one happy part.",
                    "For a team of friends is the grandest show of all.",
                ),
            },
        },
    ],
    # -------------------------------------------------------- perseverance
    "perseverance": [
        {
            "id": "jumprope",
            "thing": "jump rope",
            "thing_short": "rope",
            "wrong_feeling": "discouraged",
            "prose": {
                "problem_setup": (
                    "{short} wanted to jump rope.",
                    "Swish, hop! It looked so easy.",
                    "But the {thing_short} had other plans.",
                ),
                "problem_grows": (
                    "Trip! Tangle! Whoops!",
                    "Every try ended in a heap.",
                    "{friend_short} could do ten hops without a single wobble.",
                ),
                "wrong_choice": (
                    "{short} threw the {thing_short} down.",
                    "“I quit! I will NEVER get it!”",
                    "Quitting felt easy — and heavy, both at once.",
                ),
                "consequence": (
                    "The {thing_short} lay still and quiet.",
                    "Watching the others hop stung a little.",
                    "Wishing, {short} discovered, is not the same as trying.",
                ),
                "guidance": (
                    "“Every expert began by failing,” said {mentor_short}.",
                    "“Fall down seven times? Stand up eight.”",
                    "“Little tries stack up like blocks into big wins.”",
                ),
                "making_right": (
                    "{short} picked the {thing_short} back up.",
                    "One hop. Trip. Two hops. Trip. THREE hops!",
                    "Every stumble taught {short}'s feet a brand-new secret.",
                ),
                "lesson": (
                    "Hop, hop, hop — ten in a row!",
                    "{short} never gave up again.",
                    "For trying one more time is how every wonder is done.",
                ),
            },
        },
        {
            "id": "den",
            "thing": "leafy little den",
            "thing_short": "den",
            "wrong_feeling": "discouraged",
            "prose": {
                "problem_setup": (
                    "{short} was building a den.",
                    "Sticks up, leaves on top — ta-da!",
                    "It was going to be the coziest spot in {place}.",
                ),
                "problem_grows": (
                    "Whoosh! The wind knocked it down.",
                    "{short} built it again. CRASH — again!",
                    "Three times built, three times tumbled.",
                ),
                "wrong_choice": (
                    "{short} kicked the sticks away.",
                    "“Silly den! I give up!”",
                    "{short} plopped down with folded arms and a thundercloud frown.",
                ),
                "consequence": (
                    "No den meant no cozy spot.",
                    "The pile of sticks just lay there.",
                    "Given-up dreams cannot build themselves.",
                ),
                "guidance": (
                    "“Try a new way,” said {mentor_short}.",
                    "“Strong things are built try by try.”",
                    "“When it falls, you have not failed — you have learned.”",
                ),
                "making_right": (
                    "{short} studied the sticks carefully.",
                    "Big ones first! Criss-cross! Pat the leaves down!",
                    "This time, the {thing_short} stood proud against the breeze.",
                ),
                "lesson": (
                    "The {thing_short} stood strong at last.",
                    "Every tumble had taught {short} something.",
                    "For dreams are built by hearts that try just one more time.",
                ),
            },
        },
    ],
}

# Rhyming couplets for the moral-specific beats.  Each moral's couplets tell
# one specific scenario's storyline (see MORAL_RHYME_SCENARIO below), so in
# rhyme mode that scenario is always the one selected -- keeping slot words
# and the lesson page in step with the verses.  A moral may also override a
# generic beat here (e.g. courage overrides "decision").  Rhyme words are
# fixed so the rhymes always land.
MORAL_RHYMES: dict[str, dict[str, str]] = {
    "sharing": {
        "problem_setup": "“May I have a turn?” asked {friend_short} that day,\n“just one little go, and then we can play!”",
        "problem_grows": "But {short} held on, oh ever so tight:\n“What if it's gone by tomorrow night?”",
        "wrong_choice": "“No, it is MINE!” said {short} with a frown,\nand {friend_short}'s happy face fell right down.",
        "consequence": "Alone with the {thing_short}, the game felt small,\nfor with no one to share, it's no fun at all.",
        "guidance": "“Shared things grow sweeter,” the old friend said,\n“for joy doubles up when it's spread and spread.”",
        "making_right": "“Here, you go first!” said {short} with a smile,\n“and let's play together a long, long while!”",
        "lesson": "So share what you love, give joy away —\nit dances right back, twice as bright, they say.",
    },
    "kindness": {
        "problem_setup": "Then somebody stumbled and started to cry,\nbut everyone else went hurrying by.",
        "problem_grows": "The tears rolled down, one, two, and three:\n“Won't anyone stop? Won't anyone see?”",
        "wrong_choice": "“No time!” said {short}, “I'm off to play!”\nand hurried past, looking the other way.",
        "consequence": "But games feel empty and prizes feel small,\nwhen a friend sits crying beside the wall.",
        "guidance": "“Kind hearts stop to help,” the wise one said,\n“choose a friend in need over games ahead.”",
        "making_right": "“Are you okay? Here, lean on me!”\n{short} helped up gently, as gently could be.",
        "lesson": "So be soft, be gentle, be quick to care,\nfor kindness is sunshine we all can share.",
    },
    "honesty": {
        "problem_setup": "Oh no! A crash and a clatter and — oh!\nHow did it happen? Well... {short} did know.",
        "problem_grows": "Somebody's coming! Oh, what to do?\nTell them the truth, or fib a fib or two?",
        "wrong_choice": "“It wasn't me!” — the little fib flew,\nbut deep down inside, {short} knew and knew.",
        "consequence": "A fib is a stone you carry all day,\nit sits in your tummy and won't go away.",
        "guidance": "“The truth,” said the wise one, “is light as a feather,\na mistake plus the truth can be mended together.”",
        "making_right": "“It was me, I am sorry,” said {short} at last,\nand the heavy old stone melted away so fast.",
        "lesson": "So tell the truth, though your voice may shake,\nit's the bravest, kindest choice to make.",
    },
    "patience": {
        "problem_setup": "“I want it NOW!” {short} started to shout,\n“why must the waiting stretch out and out?”",
        "problem_grows": "Tick went the clock, so slow and so small,\nas if time weren't moving along at all.",
        "wrong_choice": "{short} couldn't wait — not one minute more,\nand rushed right ahead like never before.",
        "consequence": "But hurrying spoiled the fun that day,\nfor rushed little joys just crumble away.",
        "guidance": "“Good things grow slowly,” the wise one said,\n“so water, and wait, and dream ahead.”",
        "making_right": "So {short} sat quietly, counting to ten,\nand waited, and waited, and smiled again.",
        "lesson": "For sweetest of all are the joys that come late —\nthe loveliest things are worth the wait.",
    },
    "courage": {
        "problem_setup": "A {thing} stood right in the way,\nand {short}'s brave smile wobbled that day.",
        "problem_grows": "“You're too little,” the worry-thoughts said,\nas shivery shakes filled {short}'s head.",
        "wrong_choice": "“I can't!” cried {short}, and turned to hide,\nwith a scared little wobble deep inside.",
        "consequence": "But hiding away from every fear\nmeans missing the fun when it's oh-so-near.",
        "guidance": "“Take one deep breath and one small step, dear —\neach little step makes the way more clear.”",
        "decision": "{short} took a breath and stood up tall:\n“Being scared won't stop me after all!”",
        "making_right": "One step, two steps — don't look down!\nAcross the {thing_short}! The bravest in town!",
        "lesson": "So when you feel scared, stand strong and tall,\none brave little step is the biggest of all.",
    },
    "obedience": {
        "problem_setup": "“Stay close,” said {mentor_short}, “and listen well,”\nbut the wide world sparkled like a magic spell.",
        "problem_grows": "“Just one little peek,” {short} whispered low,\n“one hop past the gate — who ever will know?”",
        "wrong_choice": "Away went {short} with a skip and a bound,\ntill nothing familiar could be found.",
        "consequence": "“Oh dear, I am lost, and the sky's turning gray,\nI wish I had listened and chosen to stay.”",
        "guidance": "“Rules are like hugs,” said the wise one, “you see,\nthey're made out of love to keep you safe with me.”",
        "making_right": "“I'm sorry, I'll listen,” said {short} that night,\nand home they went as the stars turned bright.",
        "lesson": "So listen to those who love you true,\nfor rules are arms wrapped safe around you.",
    },
    "politeness": {
        "problem_setup": "There were treats to share and games to play,\nbut somebody's manners had run away.",
        "problem_grows": "The wanting grew bigger — a rumbly roar —\ntill {short} forgot what manners were for.",
        "wrong_choice": "“GIMME!” cried {short} with a grab and a shout,\nand all of the cozy warmth drained out.",
        "consequence": "For nobody smiles at a push and a grab,\nand snatched-away treats taste terribly drab.",
        "guidance": "“Please and thank you,” the wise one told,\n“are tiny words made of purest gold.”",
        "making_right": "“May I please have a turn?” asked {short}, sweet and low,\nand every face lit up with a glow.",
        "lesson": "So sprinkle your words with please and thank you,\nand watch all the smiles come dancing to you.",
    },
    "gratitude": {
        "problem_setup": "A present arrived for {short} one day,\nbut a grumble chased all the thankfulness away.",
        "problem_grows": "“It's small,” {short} sighed, “as plain as can be —\nthis isn't the gift that was wished for by me.”",
        "wrong_choice": "No thank-you was said, not even a smile,\nand the giver looked down at the ground for a while.",
        "consequence": "The whole day after felt chilly and small,\nfor grumbly hearts find no joy at all.",
        "guidance": "“Count the love, not the size,” the wise one said,\n“see gifts with your heart instead of your head.”",
        "making_right": "“Thank you, dear friend! It's warm as a hug!”\nsaid {short}, all wrapped up cozy and snug.",
        "lesson": "So look for the gifts in each little thing,\na thankful heart makes the whole world sing.",
    },
    "teamwork": {
        "problem_setup": "There stood a job as big as could be,\ntoo big for one — just wait and see.",
        "problem_grows": "“I'll do it myself!” said {short} with a huff,\n“I'm strong and I'm clever and that is enough!”",
        "wrong_choice": "Push, pull, wobble — CRASH and BUMP!\nDown sat {short} in a puffed-out slump.",
        "consequence": "The big job sat there, not budging at all,\nfor one little helper alone is too small.",
        "guidance": "“Many hands make light work,” the wise one smiled,\n“so call to your friends, my dear little child.”",
        "making_right": "“Please help!” called {short}, and friends came round —\nheave-ho, heave-ho — it moved with one bound!",
        "lesson": "So build with your friends, together as one,\nfor teamwork turns hard into happy and done.",
    },
    "perseverance": {
        "problem_setup": "{short} tried something brand-new that day,\nbut oh, it would not go {short}'s way.",
        "problem_grows": "A trip! A tangle! A tumble! A fall!\nIt seemed like no progress was made at all.",
        "wrong_choice": "“I QUIT!” {short} shouted, and stomped on the ground,\nand threw the whole grumpy day down in a mound.",
        "consequence": "But quitting, {short} found, has a strange little sting,\nfor give-up days never learn anything.",
        "guidance": "“Try one more time,” the wise one said,\n“for each little stumble's a step ahead.”",
        "making_right": "One more try, then two, then three,\ntill {short} cried out: “Look! Look at me!”",
        "lesson": "So try one more time when you stumble or fall,\nfor one-more-try hearts can do anything at all.",
    },
}

# The scenario whose storyline each moral's rhyme couplets tell.  Rhyme-mode
# stories always use this scenario so beats, slot words, and the lesson page
# all describe the same tale.
MORAL_RHYME_SCENARIO: dict[str, str] = {
    "sharing": "kite",
    "kindness": "tumble",
    "honesty": "flowerpot",
    "patience": "seed",
    "courage": "bridge",
    "obedience": "gate",
    "politeness": "picnic",
    "gratitude": "scarf",
    "teamwork": "pumpkin",
    "perseverance": "jumprope",
}

# Warm summary for the dedicated "Lesson of the Story" page, keyed by moral
# and then by scenario id so the recap always matches the story that was
# actually told (e.g. politeness/"storytime" teaches listening, not the
# magic words of politeness/"picnic").
MORAL_LESSONS: dict[str, dict[str, str]] = {
    "kindness": {
        "tumble": "Kind hearts make the world softer. When you stop to help a friend, you give the best gift of all.",
        "newcomer": "Kindness always goes first. One warm hello can turn a stranger into a friend and light up a whole day.",
    },
    "honesty": {
        "flowerpot": "The truth may feel wobbly to say, but it always makes your heart feel light. Brave friends tell the truth.",
        "cookie": "A little fib grows heavy, but owning up makes your heart feel light again. Honesty is the sweetest recipe of all.",
    },
    "sharing": {
        "kite": "Everything lovely is twice as lovely when it is shared. A turn for a friend always comes back with a smile.",
        "berries": "A treat that is shared feeds two hearts at once. The sweetest bite is always the one you give away.",
    },
    "patience": {
        "seed": "Good things grow slowly. When you wait kindly and calmly, you make room for wonderful surprises.",
        "swing": "Turns come to those who wait. When you wait kindly and cheer for your friends, the fun swings higher than ever.",
    },
    "courage": {
        "bridge": "Being brave does not mean you are not scared. It means taking one small step anyway — and growing bigger inside each time.",
        "hollow": "Shadows are smaller than they look. Courage is a little lantern — hold a friend's hand, take one brave step, and it lights the way.",
    },
    "obedience": {
        "gate": "Rules from people who love you are hugs made of words. Little ears that listen keep little hearts safe.",
        "bedtime": "When someone who loves you calls you in to rest, they are caring for you. Sleep that comes when called brings mornings full of play.",
    },
    "politeness": {
        "picnic": "‘Please’ and ‘thank you’ are tiny golden keys. They open doors, warm hearts, and keep friendships sparkling.",
        "storytime": "Ears first, words second. When you listen and wait for your turn to speak, your words grow sweeter — and friends love to listen back.",
    },
    "gratitude": {
        "scarf": "A thankful heart finds treasure everywhere. When you count the love inside each little thing, every day becomes a gift.",
        "rainyday": "Even a gray day hides little gifts. Thankful eyes turn raindrops into music and puddles into tiny mirrors full of sky.",
    },
    "teamwork": {
        "pumpkin": "Some jobs are too big for one, and that is okay! Friends who work together turn impossible into easy-peasy.",
        "parade": "A team shines like a whole sky of stars. When every friend has a part to play, the day becomes a grand parade.",
    },
    "perseverance": {
        "jumprope": "Everyone stumbles when they try something new. Hearts that try one more time can do anything at all.",
        "den": "When something tumbles down, you have not failed — you have learned. Dreams are built by hearts that try just one more time.",
    },
}


# ---------------------------------------------------------------------------
# Beat plans + visuals
# ---------------------------------------------------------------------------

BEATS_12 = [
    "intro", "joy", "friend", "problem_setup", "wrong_choice", "consequence",
    "feelings", "mentor", "guidance", "making_right", "celebration", "lesson",
]
BEATS_16 = [
    "intro", "joy", "friend", "activity", "problem_setup", "problem_grows",
    "wrong_choice", "consequence", "feelings", "mentor", "guidance",
    "decision", "making_right", "reaction", "celebration", "lesson",
]

MORAL_BEATS = {
    "problem_setup", "problem_grows", "wrong_choice", "consequence",
    "guidance", "making_right", "lesson",
}

# beat -> (expression, pose, friend_expr, show_friend, show_mentor,
#          composition, time_of_day, shot)
# The time-of-day and shot columns trace a visual arc across the book:
# a bright morning open, an overcast dip at the low point, and a golden-hour
# celebration -- while the camera moves wide -> close -> vista, page to page.
BEAT_VISUALS: dict[str, tuple[str, str, str, bool, bool, str, str, str]] = {
    "intro":         ("excited", "wave", "happy", False, False, "center", "morning", "establish"),
    "joy":           ("excited", "jump", "happy", False, False, "left", "day", "wide"),
    "friend":        ("happy", "wave", "excited", True, False, "right", "day", "wide"),
    "activity":      ("excited", "arms_up", "happy", True, False, "center", "day", "corner"),
    "problem_setup": ("surprised", "point", "happy", True, False, "left", "day", "wide"),
    "problem_grows": ("worried", "stand", "happy", False, False, "closeup", "day", "close"),
    "wrong_choice":  ("sad", "stand", "sad", True, False, "right", "day", "wide"),
    "consequence":   ("sad", "stand", "sad", False, False, "left", "overcast", "corner"),
    "feelings":      ("sad", "stand", "sad", False, False, "closeup", "overcast", "close"),
    "mentor":        ("curious", "stand", "happy", False, True, "left", "day", "wide"),
    "guidance":      ("curious", "stand", "happy", False, True, "right", "day", "corner"),
    "decision":      ("excited", "point", "happy", False, False, "closeup", "day", "close"),
    "making_right":  ("happy", "hug", "excited", True, False, "center", "day", "path"),
    "reaction":      ("giggling", "arms_up", "excited", True, False, "left", "day", "wide"),
    "celebration":   ("excited", "jump", "excited", True, True, "center", "sunset", "hill"),
    "lesson":        ("happy", "wave", "happy", False, False, "center", "sunset", "wide"),
}

# How the book journeys through a world's sub-locations (zone indices into
# SETTING_ZONES): home for the setup & the return, a second spot while the
# problem unfolds, and the highest/third vista for the celebration.  Keeps a
# sense of travel while staying inside one coherent world.
_BEAT_ZONE_IDX: dict[str, int] = {
    "intro": 0, "joy": 0, "friend": 0, "activity": 0,
    "problem_setup": 1, "problem_grows": 1, "wrong_choice": 1,
    "consequence": 1, "feelings": 1, "mentor": 1,
    "guidance": 2, "decision": 2,
    "making_right": 0, "reaction": 0,
    "celebration": 0, "lesson": 0,
}


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _species_label(key: str) -> str:
    return key.replace("_", " ").title()


def _prose_for_band(sentences: tuple[str, ...], age_band: str) -> str:
    if age_band == "2-4":
        return sentences[0]
    if age_band == "4-6":
        return " ".join(sentences[:2])
    return " ".join(sentences)


def _zone_journey(setting: str, seed: int) -> dict[int, str]:
    """Map zone-indices 0/1/2 to concrete sub-locations of *setting*.

    Index 0 is always the world's home zone; the two "away" zones are shuffled
    by seed so different books wander to different spots of the same world.
    """
    from src.books.scenes import SETTING_ZONES

    zones = list(SETTING_ZONES.get(setting, ("greens",)))
    home = zones[0]
    others = zones[1:] or [home]
    r = random.Random(seed * 1000003 + 17)
    r.shuffle(others)
    return {
        0: home,
        1: others[0],
        2: others[1] if len(others) > 1 else others[0],
    }


def _cast(params: dict, rng: random.Random) -> tuple[str, str, str, str]:
    """Pick friend + mentor (deterministic; avoids species clashes).

    Returns (friend_key, friend_name, mentor_key, mentor_name).
    """
    from src.books.illustrator import load_book_config

    bp = load_book_config().get("book_params") or {}
    themes = bp.get("themes") or {}
    names = bp.get("character_names") or {}

    theme = params.get("character_theme", "")
    main_key = params.get("character_key", "")
    pool = [k for k in (themes.get(theme, {}).get("characters") or []) if k != main_key]
    if not pool:
        pool = ["bunny"] if main_key != "bunny" else ["bear"]
    friend_key = rng.choice(sorted(pool))
    friend_names = names.get(friend_key) or [friend_key.title()]
    friend_name = rng.choice(list(friend_names))

    setting = params.get("setting", "park")
    mentor_pool = list(SETTING_MENTOR_POOLS.get(setting, ("owl",)))
    cast_species = {main_key, friend_key}
    # rotate the pool by seed so different books get different mentors, then
    # take the first that doesn't clash with the main character or friend.
    start = rng.randrange(len(mentor_pool))
    rotated = mentor_pool[start:] + mentor_pool[:start]
    mentor_key = next((m for m in rotated if m not in cast_species), None)
    if mentor_key is None:
        mentor_key = next((m for m in MENTOR_FALLBACK if m not in cast_species), "owl")
    return friend_key, friend_name, mentor_key, MENTOR_NAMES[mentor_key]


def build_story(params: dict) -> Story:
    """Assemble the full, deterministic story for a params dict.

    Required params keys: character_key, character_theme, character_name,
    setting, moral, age_band, narrative_style, page_count, seed.
    """
    seed = int(params.get("seed", 0))
    rng = random.Random(seed + 1)

    moral = params.get("moral", "sharing")
    if moral not in MORAL_SCENARIOS:
        moral = "sharing"
    style = params.get("narrative_style", "prose")
    scenarios = MORAL_SCENARIOS[moral]
    scenario = scenarios[rng.randrange(len(scenarios))]
    if style == "rhyme":
        # The couplets tell one fixed storyline per moral; pin the scenario
        # so slot words and the lesson page match the verses.
        rhyme_id = MORAL_RHYME_SCENARIO[moral]
        scenario = next(s for s in scenarios if s["id"] == rhyme_id)

    setting = params.get("setting", "park")
    phrases = SETTING_PHRASES.get(setting, SETTING_PHRASES["park"])
    friend_key, friend_name, mentor_key, mentor_name = _cast(params, rng)

    short = params.get("character_name", "Sunny")
    species = _species_label(params.get("character_key", "friend"))
    full_name = f"{short} the {species}"

    ctx = {
        "short": short,
        "name": full_name,
        "species": species.lower(),
        "friend_short": friend_name,
        "friend_species": _species_label(friend_key).lower(),
        "mentor": mentor_name,
        "mentor_short": MENTOR_SHORT[mentor_key],
        "place": phrases["place"],
        "feature": phrases["feature"],
        "activity": phrases["activity"],
        "thing": scenario["thing"],
        "thing_short": scenario["thing_short"],
        "wrong_feeling": scenario["wrong_feeling"],
        "moral": moral,
        "seed": seed,          # lets the illustrator vary scenes between books
    }

    # Per-book zone journey: home (0) -> a second spot (1) while the problem
    # unfolds -> a third spot (2) for the turning point -> back home.  The two
    # away-zones are shuffled by seed so different books wander differently.
    zone_by_idx = _zone_journey(setting, seed)

    age_band = params.get("age_band", "4-6")
    page_count = int(params.get("page_count", 12))
    beats = BEATS_16 if page_count >= 16 else BEATS_12

    pages: list[StoryPage] = []
    for beat in beats:
        if style == "rhyme":
            template = (MORAL_RHYMES[moral].get(beat)
                        or GENERIC_RHYME.get(beat))
        else:
            sentences = (scenario["prose"].get(beat) if beat in MORAL_BEATS
                         else GENERIC_PROSE.get(beat))
            template = _prose_for_band(sentences, age_band) if sentences else None
        if template is None:  # pragma: no cover - all beats are covered
            continue
        text = template.format(**ctx)
        expr, pose, fexpr, friend, mentor, comp, tod, shot = BEAT_VISUALS[beat]
        zone = zone_by_idx[_BEAT_ZONE_IDX.get(beat, 0)]
        pages.append(
            StoryPage(
                text=text, beat=beat, expression=expr, pose=pose,
                friend_expression=fexpr, show_friend=friend, show_mentor=mentor,
                composition=comp, time_of_day=tod, shot=shot, zone=zone,
            )
        )

    return Story(
        title=params.get("display_title", f"{full_name} Learns About {moral.title()}"),
        subtitle=params.get("subtitle", f"A warm little story about {moral}"),
        pages=pages,
        lesson_heading="The Lesson of the Story",
        lesson_text=MORAL_LESSONS[moral][scenario["id"]],
        character_key=params.get("character_key", "bunny"),
        character_name=short,
        character_full_name=full_name,
        friend_key=friend_key,
        friend_name=friend_name,
        mentor_key=mentor_key,
        mentor_name=mentor_name,
        setting=setting,
        moral=moral,
        scenario_id=scenario["id"],
        context=ctx,
    )
