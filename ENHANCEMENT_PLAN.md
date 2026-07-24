# Product Generation Enhancement Plan — July 2026

**Status: Wave 1 (P1–P3) IMPLEMENTED 2026-07-10; Waves 2–5 are still plan-only.**
Wave 1 shipped academic-year builds, the date-mode trio, and hyperlink-merchandising
mockups + realized pricing (see the Wave 1 table below). The golden classic stays
byte-identical; nothing auto-publishes (generation still stops at REVIEW_PENDING).

Produced 2026-07-10 from a 32-agent deep-research run: 5 market researchers
(planner demand, visual aesthetics, kids products, adjacent product types,
listing conversion) produced 53 findings; the top 25 were independently
fact-checked by adversarial verifier agents (**16 hold / 9 weak / 0 refuted**);
a synthesis agent mapped the verified demand onto this codebase's actual
extension points. Only claims that survived verification drive priorities;
"weak" claims are used directionally or rejected.

---

## 1. Verified market landscape (the short version)

1. **The back-to-school window is open NOW.** NRF: 52–67% of BTS buying is
   done by July. Etsy academic-year (Aug 2026 – Jul 2027) teacher/student
   planners are actively transacting. Highest-urgency signal in the research.
2. **Bestsellers bundle date modes in ONE listing** — "2026 2027 & Undated …
   With Digital Stickers" is the live winning pattern (not separate SKUs).
   Undated sell-through 95% vs 83% dated. 2027-dated listings are already up.
3. **ADHD is still the strongest planner niche** (independent market reports,
   ~10% CAGR; 6,000+ review incumbent) but crowded at the head term —
   differentiation comes from named tools (dopamine menu) and dark-mode
   colorways, not from entering the keyword.
4. **Aesthetics are the strongest verified whitespace.** All five researched
   lanes HELD: Dark Academia/Poetcore (Pinterest Predicts), Châteaucore (Etsy
   first-party, +26,000% searches), Gothmas (Etsy first-party; list Aug/Sep),
   Neo Art Deco (Pinterest + Deco centennial), Messy Coquette (Etsy official,
   +500% bow searches). **Our current presets map to the DECLINING segments**
   (generic minimalism −15%, basic boho −10%).
5. **Pricing reality:** the "$25–60 premium tier" claim is WEAK. Realized
   prices are **$7–16** after Etsy discount culture. Fee math still favors
   bundles ($0.45 fixed per order). Our current $5.99 default is *below* the
   verified realized band → anchor list ~$19.99 with a standing ~30% sale.
6. **Kids products:** Montessori busy books, bold-and-easy coloring, name
   tracing, personalized name-as-hero books (Penguin Random House acquired
   Wonderbly), and SEL/emotions content all HOLD — each heavily saturated,
   each needing a differentiation angle we actually have (cohesive kawaii
   system, human-reviewed personalization).
7. **Our verified structural moats:** zero-marginal-cost hyperlinking (24–27
   links/page vs competitors' hours of manual work), the palette/preset
   machinery, the 45-character kawaii registry, and a pre-wired but unused
   `is_dark` palette lane.

Meta-signal from all 25 fact-checks: demand is real everywhere, but so is
saturation. The plan therefore never "enters a category" — every item either
deepens an existing niche, fills a verified aesthetic gap, or weaponizes a
moat competitors can't cheaply copy.

---

## 2. Roadmap — 16 enhancements in 5 waves

Priorities (P1–P16) come from the synthesis; waves group them by seasonal
deadline and dependency. Effort: S/M/L.

### Wave 1 — NOW (mid-July): catch the back-to-school window

| P | Enhancement | Effort | Modules |
|---|---|---|---|
| 1 | **Academic-year dated builds (Aug 2026 – Jul 2027)** for teacher + student. `start_month/start_year` on PlannerSpec (defaults keep golden classic byte-identical); months run Aug→Jul; cover renders "2026-2027"; academic keywords into niches.yaml; orchestrator generates these two niches first this month. | M | pages.py, generator.py, orchestrator.py, niches.yaml |
| 2 | **Date-mode trio in ONE listing zip**: `date_mode ∈ {dated_2026, dated_2027, undated}`. Undated = fill-in "Month ____ 20__" headers, same hyperlink graph. Zip = hero palette × 3 date modes + other colorways × (2027 + undated). Title pattern "2026 2027 & Undated". | M | pages.py, orchestrator.py, bundler.py, mockups.py |
| 3 | **Hyperlink merchandising + realized pricing.** Two new truthful mockups: (a) *nav-map* — page thumbnails + arrows + stat chip computed from the real link graph ("2,400+ hyperlinks"); (b) *filmstrip* — cover→index→month-tab→weekly. Title template leads with "Hyperlinked". Pricing: planner bundle list $19.99 w/ standing 30% sale (≈$13.99 realized), flagship $24.99, book $6.99, floor $4.99. | S | mockups.py, seo.py, listing.py, orchestrator.py |

**Why first:** P1/P2 are the two verified seasonal deadlines; P3 multiplies
every listing that follows. All three touch overlapping modules — build
together, one release.

### Wave 2 — July–Aug: differentiation inside existing niches

| P | Enhancement | Effort | Modules |
|---|---|---|---|
| 4 | **Dark-mode palette lane** — first-ever `is_dark` palettes: `midnight_slate` (#1A1D24 bg, patina-adjacent accents) + `dark_rainbow` (#16141C bg, dopamine accents #FF6B6B/#FFD166/#06D6A0). Wire to midnight + noir presets; dark_rainbow → adhd preferred. Merchandise as "Dark Mode". *The cheapest verified-demand slot in the codebase — capability is built and tested, zero palettes use it.* | S | templates.yaml, designs.py, niches.yaml |
| 5 | **ADHD deepening**: new `dopamine_menu` niche page (Quick wins 5min / Boosts 15min / Big treats 1hr+ columns, "today's pick" box, mood-faces energy scale) as 7th ADHD page; impulse-buy checklist (item/cost/48h-wait/still-want?) folded into `parking_lot`. Copy: "designed for how your brain works" (never "science-based" — unverifiable). | S | niche_pages.py, niches.yaml, seo.py |
| 6 | **2026 trend palette pack + linen texture**: `butter_yellow` (is_pastel), `cocoa_sage`, `transformative_teal` palettes (hex specs in synthesis); new `linen` texture token (0.3pt hairline crosshatch, 6pt, 3–4% ink) with validator fallback→dot. Palette names go into tags — 2026 color names are literal search queries. | M | templates.yaml, designs.py, styles.py, pages.py |

### Wave 3 — Aug–Sep: four new aesthetic presets (Q4 selling season)

All four fill verified gaps; each is one `_p()` line + one palette + PRESET_PALETTES entry. Rotation picks them up automatically.

| P | Preset | Aesthetic (verified) | Recipe | Palette |
|---|---|---|---|---|
| 7 | **athenaeum** | Dark Academia / Poetcore — peaks back-to-school/autumn | binder/boxed/botanical/serif/ink-on-paper/editorial/ruled | `oxblood_parchment` (#5C1A1B oxblood, #B08D3E gold, #F2E8D5 parchment) |
| 8 | **nocturne** | Gothmas / romantic goth — **list by Aug/Sep** (Etsy first-party data); we already own the celestial motif family | flat/boxed/celestial/serif/ink-on-paper/pattern/dot | `gothic_plum` (is_dark: #1D1626 bg, silver, lavender) — needs P4 lane |
| 9 | **marquee** | Neo Art Deco — strongest-verified aesthetic (Pinterest Predicts + Deco centennial); most vector-native | poster/columns/geometric/grotesk/filled-blocks/band/blank | `deco_noir` (is_dark: near-black + two-tone champagne gold + emerald) — needs P4 lane |
| 10 | **heirloom** | Châteaucore / Grandmillennial (Etsy first-party) — tag both "chateaucore" and "grandmillennial" | binder/airy/botanical/script/soft-wash/arch/dot | `toile_cream` (#F5EFE0 cream, #3E5C76 toile blue, ochre) |

### Wave 4 — Sep–Oct: content + packaging depth

| P | Enhancement | Effort | Modules |
|---|---|---|---|
| 11 | **Budget `savings_challenge` page** (7th budget page): 52-week grid + target box + 3 sinking-fund jars with progress bars + no-spend strip. Undated cells (works in all date modes). Ships ahead of the verified Dec–Jan peak to seed reviews. | S | niche_pages.py, niches.yaml |
| 12 | **Quick-start + thank-you/review pages** in every product (gated behind `include_support_pages`, default False → golden classic untouched; orchestrator sets True for new products). Addresses the #1 documented complaint ("downloaded it, don't know what to do") + the only automatable review touchpoint. Plain ask, no incentives (Etsy rules). Books: review line + coloring-page announcement on "The End" page. Standalone how-to PDF in every zip. | S | pages.py, books/generator.py, bundler.py, orchestrator.py |
| 13 | **Vector sticker packs** — new `marketing/stickers.py`: 40–50 elements/palette from OUR existing vector assets (weekday chips, checkboxes, priority dots, habit grids + motif glyphs, kawaii faces), rasterized from our own vectors via PyMuPDF @300dpi with alpha → pre-cropped PNGs + sticker-sheet PDF. In every planner zip ("+ Digital Stickers" title suffix) + standalone $4.99 packs. *Defensive: bestsellers make this table stakes.* | M | stickers.py (new), bundler.py, mockups.py, orchestrator.py |

### Wave 5 — Q4: books + the first new product line

| P | Enhancement | Effort | Modules |
|---|---|---|---|
| 14 | **SEL book content**: `big_feelings` + `brave_first_day` morals (full prose/rhyme beat scenarios per age band); bonus "Feelings Cards" pages — 4×2 kawaii-face grid using our 8 existing expressions, dashed cut lines + a coloring variant. Backlash-proof naming ("big feelings", never "SEL"). | M | story.py, params.py, books.yaml, books/generator.py |
| 15 | **Ribbon motif family + `coquette` preset**: 6 icon fns (asymmetric bow, trailing ribbon, pearl string, scallop lace, heart, cherry pair) — remember the TRIPLE registration (motifs.MOTIFS + designs.DIMENSIONS + styles.CONTAINERS). Preset: cards/airy/ribbon/script/soft-wash/pattern/dot + `cherry_ballet` palette (is_pastel; ballet pink + cherry red). | M | motifs.py, designs.py, styles.py, templates.yaml |
| 16 | **Personalized picture books (name-as-hero), made-to-order** — the one LARGE item: name-substitution slots in story beats (syllable-safe rhyme fallback), name on cover + dedication, Etsy personalization field → order-driven generation flowing through the NORMAL state machine (human review stays mandatory — that's the trust feature vs AI-slop competitors). $12.99–14.99 vs $6.99 generic. Strongest single demand signal in the kids research (PRH acquired Wonderbly). | L | story.py, params.py, books/generator.py, orchestrator.py, dashboard/app.py, publisher/listing.py |

---

## 3. New product lines (beyond planners & books)

| Candidate | Verdict | When |
|---|---|---|
| **Bold-and-easy thick-line coloring books** (kids + adult crossover) | **Build — first new product_type.** Art engine ~free (line_art mode + 45 characters + 20 scene worlds already emit coloring pages); real cost is the orchestrator third-branch + mockup page-selection. Win via sub-niches (kawaii cottage garden, seasonal, chibi animals matching our book characters) and counted packs (24/40/50 pages) — NOT generic mandala volume. | After Waves 1–2, targeting the Dec–Jan coloring peak |
| **Montessori busy books / toddler learning binders** | Build later. Best non-faddish demand driver (homeschool 5.4%/yr structural growth) but needs new layout primitives (cut lines, matching slots, velcro zones) and the PLR-commoditization answer is our cohesive kawaii style across 100+ pages. | Q4 2026 (catches holiday gifting + January homeschool restock) |
| **Card-grid engine** (emotion flashcards / affirmation lunchbox cards / Montessori 3-part cards) | Validate first via P14's bonus feelings cards at zero listing risk; if reviews mention the cards, promote to standalone packs + "Big Feelings Kit" bundle (book + cards + chart). | Gate on P14 review signal |

## 4. Rejected — do NOT build (verified reasons)

1. **Adult mandala mega-bundles** — PLR-commoditized race to zero.
2. **Wall-art / nursery print bundles** — single-SEO-site evidence, keyword trending down, JPEG multi-ratio delivery we'd have to build.
3. **Shadow-work journal line** — 2023–24 wave; incumbent backed by Simon & Schuster; saturated.
4. **Wedding invitation / Canva-template packs** — the product IS buyer self-serve editability (Canva/Templett/Corjl); static PDF can't deliver it.
5. **Neo-Y2K chrome preset** — low confidence; gradients/gloss render cheap in fpdf2. Watch-list.
6. **$25–60 premium pricing** — realized prices are $7–16; encoded instead as $19.99-list + standing sale (P3).
7. **Portrait orientation variant** — unverified + deepest-possible layout change. Revisit for 2027–28 academic cycle on review demand.
8. **Calendar deep-link annotations** — one-listing evidence. Cheap fast-follow experiment at most.
9. **Hyper-niche "system" planners** (content creator / coach / realtor) — circular SEO-listicle evidence. Homeschool is the one candidate to revisit after busy-book validation.
10. **"Lite" 30–40-page SKUs** — collides with the test-enforced page structure; P12's quick-start captures most of the value at ~5% of the effort.
11. **Listing videos** — we can't produce video (hard constraint); stat was folklore. *Human note: manually recording one 15-sec screen capture per hero listing is still worthwhile.*
12. **"That Girl" wellness overhaul** — unverified single-blog numbers; coquette (P15) serves the same buyer with Etsy-verified demand.

---

## 5. Implementation guardrails (from the constraint audit)

- **Golden classic is byte-locked** (`tests/planner/test_golden_classic.py`): every new spec param defaults to today's behavior (`start_month=1`, `include_support_pages=False`, `date_mode=dated_2026`). Never edit the fixture.
- **Motif tokens need TRIPLE registration**: `motifs.MOTIFS` + `designs.DIMENSIONS['motif']` + `styles.CONTAINERS` — missing one silently repairs to botanical or KeyErrors.
- **Niche→motif policy** (test-enforced): themed niche tuple = (themed primary, geometric, minimal).
- **Niche page shape**: 5–7 pages per niche (P5 and P11 take ADHD/budget from 6→7 — at the bound, don't exceed).
- **Searchable-tracking clamp** (0.12× font size) applies to any new text-bearing style; 'January' search regression test per preset.
- **Palette lane rules**: pale fills ⇒ `is_pastel` (pinned dark ink); dark grounds ⇒ `is_dark` (raw `paper_c`); never pure-white backgrounds.
- **Design rotation & bundles**: no preset repeats within window = len(PRESETS)−1 (adding 6 presets widens it automatically); palette bundle never empty, hero first.
- **Band-cover dispatch is total over inks** — adding a new *ink* token requires a new band structure (no new inks are planned; all new presets use existing tokens).
- **State machine is inviolable** — P16's made-to-order flow must pass through REVIEW_PENDING like everything else.
- **Book rules**: (character, setting, moral) uniqueness (P16 personalized orders exempt — same triple + different name is distinct); 2–4 age band stays single-subject; unknown characters draw `_blob`, never crash.
- **20MB file cap**; classic-named output files unchanged; all display text through `humanize()`.

## 6. Seasonal calendar (what gates what)

| Deadline | Item |
|---|---|
| **Mid-July (now)** | Wave 1 live: academic-year teacher/student listings (52–67% of BTS buying is already done — remainder disperses through September) |
| **Aug–Sep** | Nocturne/Gothmas preset listed (Etsy first-party ramp); 2027-dated bundles live |
| **Oct–Nov** | Sticker packs + support pages in all zips; coloring-book line listed for gift season |
| **Dec–Jan** | Savings-challenge page riding the New-Year budget peak; coloring peak; 2027 planner peak (date-trio bundles already live) |
| **Q4 → Jan** | Busy-book line for holiday gifting + January homeschool restock |

## 7. Effort summary

- **Small (7):** P3, P4, P5, P7, P8*, P9*, P10, P11, P12 (*after P4 lands)
- **Medium (7):** P1, P2, P6, P13, P14, P15 + coloring-book line
- **Large (2, the plan's cap):** P16 personalized books; busy-book line (later)

Waves 1–3 (P1–P10) are ~2–3 focused implementation sessions and cover every
seasonal deadline. Waves 4–5 can follow at normal cadence.

---

*Research provenance: workflow `wf_9482ad12-8eb` (32 agents, ~981k tokens,
294 tool calls). Full per-agent findings, fact-check verdicts and the
capability audit are in the session transcript; the 25-claim verdict map is
reproduced in section 1 and inline in each enhancement's rationale.*

---

## Addendum 2026-07-24 — sticker / movable-book deep-research (verified)

104-agent run (`wf_b73e4014-fb4`): 65 claims → 25 adversarially verified
(3-vote), 19 confirmed / 6 refuted / 0 unverified. Owner-prompted by reports
of digital-sticker and velcro movable-character-book trends.

**P13 (sticker packs) — pull the IN-ZIP half forward to NOW; keep standalone
packs at Sep–Oct.** Verified: every top 2026 planner listing bundles
2,500–3,500+ pre-cropped PNG stickers (often + a .goodnotes sticker book)
*inside* the planner purchase and titles it "With Digital Stickers"
(listings 1833235300, 1847039141, 1639453781 et al.) — table stakes at the
top of the niche. Our academic trio listings should NOT launch without
stickers in the zip. Nuances: (i) "mega-library-size is the only winning
format" was REFUTED 0-3 — curated packs stay viable; (ii) top sticker themes
are ADULT planner aesthetics (Navy & Blush, Inspirational Quotes, Clean All
The Things…), NOT kids/kawaii → our packs should lead with palette-matched
functional elements (chips/checkboxes/habit grids per the P13 spec); kawaii
character stickers are a differentiated bet, not proven demand; (iii)
competitor counts are combinatorial (elements × colors) — we can honestly
advertise "150+ stickers" by counting per-palette variants; (iv) name more
apps explicitly (GoodNotes, Notability, Xodo, Noteshelf…) — category-standard
compatibility copy.

**Busy-book line — KEEP Q4 timing.** The movable-character TikTok wave is
Feb-2023 vintage (video Snowflake-ID decode) and was already in TikTok-Shop
commodity-affiliate phase by Oct 2025 — no current-virality basis to pull
forward. But the category is confirmed digital-addressable at premium price:
a pure-PDF busy book lists at **$55 for 129 activities / 250+ pages**
(listing 770011334, Star Seller ~39.7k sales) with print-laminate-velcro
assembly delegated to the buyer. Spec updates for the Q4 build: target
100+ pages (40-page starters exist but under-differentiate), and ship BOTH
variants from the same art — velcro-assembly AND "no-prep print-and-go"
(verified counter-position, listing 4319559470).

**OWNER PRICING DECISION 2026-07-24 (overrides P3's pricing half):** volume
strategy — planners **$5.99** flat, books **$4.99**; deliberately NOT the
research-recommended $19.99-list + standing-30%-sale anchor. Priced to sell
many, not high. P3's merchandising half (hyperlink mockups, "Hyperlinked"
titles) stays live. Do not re-raise prices without the owner's say-so.

**No new Q4 trend surfaced.** Etsy's own S/S-2026 trend report contains zero
digital-download/kids content (weak negative — it structurally skews
physical). Refuted as folklore: "174k monthly views / $2–6k/mo sticker
sellers" and "100–500-sticker $5–12 sweet spot" (both from a PLR blog).
Open: realized prices behind Etsy's bot-wall; whether kids-themed digital
stickers are a gap or a no-demand zone; Q4 seasonal sticker/busy-book angles.
