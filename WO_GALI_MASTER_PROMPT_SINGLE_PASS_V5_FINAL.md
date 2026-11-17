# वो गली (WO GALI) — Single-Pass Master Prompt V5 FINAL (8-Rule Audited + Hard 55-Second Ceiling)

यह फाइनल V5 दोनों ड्राफ्ट (`WO_GALI_MASTER_PROMPT_SINGLE_PASS_V5.md` और `gemini-code-1794931977772.md`) को मिलाकर बनाया गया है। आठों नॉन-नेगोशिएबल नियम और नया **55.0 सेकंड हार्ड अपर लिमिट** इसमें लॉक हैं।

## हार्ड 55-सेकंड सीलिंग (सबसे ऊपर का नियम)

- फाइनल Viraj MP3 वॉइसओवर और पूरी `VID-01..N` टाइमलाइन कभी भी **55.0 सेकंड** से ज्यादा नहीं होगी (`<= 55.0s` अंतिम सीमा)।
- टारगेट विंडो: **48.0s से 53.0s**।
- Section A वॉइस स्क्रिप्ट: **550 से 590 अक्षर** (हार्ड लॉक)। 48.0s की टारगेट विंडो में रहने के लिए 570 से 590 अक्षर का लक्ष्य रखें।
- कैलिब्रेशन रेट: **11.8 अक्षर प्रति सेकंड** (पुराना माप: 614 अक्षर ≈ 52s)। 590 अक्षर ≈ 50.0s, 550 अक्षर ≈ 46.6s।
- `wo_gali_validator.py` यही नियम Agent 1 (स्क्रिप्ट और टाइमलाइन) और Agent 4 (असली MP3 की लंबाई) पर लागू करता है।

## वर्कफ्लो (इसी क्रम में चलाएँ)

1. **PART 1** का प्रॉम्प्ट चलाएँ: टॉप 10 नए टॉपिक्स आएँगे और Topic #01 (Episode 03) व Topic #02 (Episode 04) लॉक होंगे। चाहें तो सीधे **PART 3** की रेडीमेड लिस्ट इस्तेमाल करें।
2. **PART 2** का मास्टर प्रॉम्प्ट Topic #01 (Episode 03) के लिए चलाएँ।
3. वही PART 2 प्रॉम्प्ट केवल `STORY TOPIC:` लाइन बदलकर Topic #02 (Episode 04) के लिए चलाएँ: `STORY TOPIC: STORY 04 (Topic #02) छत पर उल्टे कदम (Chhat par Ulte Kadam)`
4. Agent 1 का आउटपुट `python wo_gali_validator.py artifact.md` से जाँचें।
5. **PART 5** की कमांड्स से Agents चलाएँ।

---

## PART 1: TOP 10 NEW TOPICS SELECTOR (Story 01 और Story 02 एक्सक्लूड)

```text
You are Claude Opus 5.5 acting as the Lead Horror Story Architect for the Hindi 2D animated YouTube Shorts channel "वो गली" (WO GALI).

COMPLETED STORIES (STRICTLY EXCLUDE THESE 2 TOPICS — DO NOT REPEAT THEIR PLOT, TWIST, OR SCENES):
1. "पापा की वीडियो कॉल" (Papa ki Video Call — late-night video call from father warning not to open the door for the courier boy, while the father is already inside the house behind the blue curtain and died three days ago).
2. "दादी की चप्पल" (Dadi ki Chappal — three AM footsteps of grandmother's slippers, fake grandmother giving a rule to keep eyes closed, backward feet under the bed while the real grandmother is in the village).

YOUR TASK RIGHT NOW:
Generate a ranked list of the TOP 10 BRAND-NEW, HIGHEST-RETENTION INDIAN EVERYDAY HORROR SHORTS TOPICS (numbered 01 to 10) for our 48 to 53 second (hard maximum 55.0 seconds, 550 to 590 character) 2D Webtoon Horror Shorts format, modeled on our 10M–30M viral reference patterns: everyday Indian house, hostel, train, metro, or lift setting + relatable family, neighbor, or stranger hook in the first three seconds + mid-story misdirection rule or warning + visual clue + shocking last-three-second double twist.

TOPIC RULES:
- No topic may reuse the plot or twist of the two completed stories: no call or message from a dead family member, no fake family member impersonating a real one, no "keep your eyes closed" rule.
- Every protagonist is a young adult (a young Indian woman or a young Indian man). No child, school, or schoolchild protagonists.
- Hindi text must be Devanagari with zero Persian or Arabic nuqta dots (write क, ख, ग, ज, फ only; native ड़ and ढ़ are allowed). Write all numbers and clock times in Hindi words.

For each of the 10 new topics, provide:
1. Topic Number and Title (Hindi + Roman Hindi)
2. Top Yellow Banner Text
3. Three-Second Opening Hook
4. Mid-Story Twist or Rule
5. Final Three-Second Shock Reveal

At the end, highlight Topic #01 (for Episode 03) and Topic #02 (for Episode 04) as today's two locked production selections, so I can run the V5 Single-Pass Master Prompt for Topic #01 and Topic #02 one by one.
```

---

## PART 2: SINGLE-PASS MASTER PROMPT V5 FINAL (Copy-Paste Ready — AWS KIRO Opus 5.5 / Gemini)

Episode 04 के लिए केवल `STORY TOPIC:` लाइन बदलें, बाकी प्रॉम्प्ट वैसा ही रखें।

```text
You are Claude Opus 5.5 acting as the Lead Horror Story Architect for the Hindi 2D animated YouTube Shorts channel "वो गली" (WO GALI).
Generate the COMPLETE 4-Section Story Blueprint in a SINGLE PASS in clean Markdown (.md) Artifact format for the following topic:

STORY TOPIC: STORY 03 (Topic #01) लिफ्ट का आईना (Lift ka Aaina)

STRICT EXCLUSION RULE:
- Do NOT reuse or copy any plot, twist, or scene from our completed episodes "पापा की वीडियो कॉल" (Papa ki Video Call) and "दादी की चप्पल" (Dadi ki Chappal).

RULE 0 — HARD 55-SECOND MAXIMUM (NEVER EXCEED 55.0 SECONDS):
- The final voiceover and the full VID-01 to VID-N timeline must NEVER exceed 55.0 seconds. Target window: 48.0s to 53.0s. Absolute hard ceiling: 55.0s.
- Duration rate: 11.8 characters per second. Total timeline = Total Character Count ÷ 11.8.

RULE 1 — SINGLE-PASS 4-SECTION OUTPUT:
- Generate all four sections (SECTION A, SECTION B, SECTION C, SECTION D) in one complete Markdown artifact right now. Do NOT stop after Section B.
- Do NOT wrap the artifact, or any part of it, in triple-backtick code fences. Use single backticks only around each IMG, VID, and D1 prompt.
- Do NOT output any square-bracket characters or any angle-bracket placeholders anywhere. Every value must be final, real content.

RULE 2 — SECTION A: STRICT 550 TO 590 CHARACTER LOCK:
- Ignore word counts. Measure ONLY the total characters of the spoken script paragraph, including spaces and punctuation, counted as Unicode characters (the same count as Python len()).
- The Hindi Voice Script MUST be between 550 and 590 characters. Aim for 570 to 590 characters so the voiceover lands inside the 48.0s to 53.0s target window.
- Section A contains ONLY the 5 required header lines (Story Name, Top Yellow Banner Text, Total Character Count, Hard Maximum Voice Duration, ElevenLabs Hindi Voice Script) plus the one continuous Hindi paragraph. NO tables, NO scene-by-scene lines, NO "Scene 01" labels, NO timings in Section A. Scene timings belong ONLY in Section C.
- Use 100% pure Hindi in Devanagari with ZERO Persian or Arabic nuqta dots: always write क, ख, ग, ज, फ without the dot. Keep top nasal marks (ं, ँ) and the native retroflex letters ड़ and ढ़.
- Write all numbers and clock times in Hindi words (for example ग्यारह बजे, never a digit). Zero digits in the script.

RULE 3 — MACHINE-PARSING CONTRACT (NEVER VIOLATE):
- Every IMG and VID prompt is ONE single bullet line: a bold header with metadata in parentheses, the colon INSIDE the bold, one space, then the full English prompt inside single backticks on the SAME line. No line breaks inside a prompt and no sub-bullets under a prompt.
- BOTH every IMG prompt AND every VID prompt are 100% self-contained: repeat the full physical description of every visible character ("a young Indian woman" or "a young Indian man", approximate age, face, hair, skin tone, clothes) and the full room or environment description in every single IMG and every single VID prompt. Never write "same as IMG-01", "same character", "previous scene", or "this exact scene" in place of the description.
- Text inside IMG and VID backticks is English only: no Devanagari, no apostrophes, and no quotation marks of any kind.

RULE 4 — GOOGLE FLOW ZERO-VOICE & SILENT LIP-SYNC LOCK (SECTION C):
- Google Flow / Veo must NEVER generate spoken voice, dialogue, or AI speech. It must generate ONLY physical background sound effects (Spot SFX).
- Inside every VID backtick prompt: NO quoted dialogue strings, NO apostrophes, NO Devanagari, and NONE of these speech-trigger words in any form: say, says, said, saying, whisper, whispers, whispering, murmur, murmuring, shout, shouting, ask, asks, asking, scream, screams, screaming, cry, cries, crying, yell, talk, talking, speak, speaks, begins to speak, when speaking, voice says, call out.
- Every VID prompt, whether or not the character is talking, MUST include: natural eye blinking, pupil movement, a specific hand action, walking or running or body motion, and this exact mandatory phrase: lips and jaw open and close in smooth natural silent visual lip-sync motion without any spoken voice
- Spot SFX must be physical, non-vocal foley only (for example Wall Clock Tick-Tock, Barefoot Footsteps on Tiles, Lift Door Metal Slide, Lift Motor Hum, Rapid Knocks on Wooden Door, Curtain Fabric Rustle, Ceiling Fan Whir, Heartbeat Thump, Heavy Sub-Bass Impact Boom, Dissonant String Stinger). NEVER use human vocal sounds such as scream, shout, whisper, giggle, laugh, sobbing, crying, humming, gasp, or breathing.

RULE 5 — CONTENT-FILTER SAFETY LOCK:
- In all English prompts (IMG, VID, D1), describe young protagonists ONLY as "a young Indian woman" or "a young Indian man". Never use girl, boy, child, kid, teen, teenager, student, schoolchild, or school uniform.

RULE 6 — SECTION D1 YOUTUBE SHORTS 9:16 SAFE-ZONE THUMBNAIL LOCK:
- The thumbnail prompt must state a strict vertical 9:16 portrait aspect ratio at 1024x1792 pixels, with all key characters, faces, and horror elements placed inside the central 80% vertical safe-zone, leaving only plain background in the outer 10% on the left and right edges so nothing is cropped on YouTube Shorts.
- The raw thumbnail image contains NO text: it must end with "No text, no captions, no watermark." Banner and hook text are added later in the editor, as described in the D1 Overlay Spec line.

REQUIRED 4-SECTION ARTIFACT STRUCTURE (use these exact section headings):

# SECTION A — STORY NAME & ELEVENLABS HINDI VOICE SCRIPT (550–590 CHARACTERS · HARD MAX 55.0s)
Write exactly these 5 header lines, then the script as one continuous Hindi paragraph on the next line. Shape example (replace the values with this story's real values):
- **Story Name:** लिफ्ट का आईना (Lift ka Aaina)
- **Top Yellow Banner Text:** Lift ka Aaina 🪞😱
- **Total Character Count:** 584
- **Hard Maximum Voice Duration:** 55.0 Seconds (estimated 49.5s at 11.8 characters per second, target 48.0s–53.0s)
- **ElevenLabs Hindi Voice Script (Nuqta-Free, 550–590 Characters):**

# SECTION B — IMAGE GENERATION PROMPTS (IMG-01 TO IMG-N)
- Generate 18 to 24 scenes. Split the Section A script into consecutive spoken phrases, in order, with no gaps and no overlaps; one IMG per phrase.
- Header metadata: scene number, character count of that phrase, approximate duration (Chars ÷ 11.8), and the spoken Hindi phrase in double quotes (in the header only, never inside the backticks).
- Shape example:
  - **IMG-01 (Scene 01 · Chars: 28 · ~2.4s · "रात के ग्यारह बजे लिफ्ट रुकी"):** `A young Indian woman, about twenty-four years old, oval face, large worried dark brown eyes, long straight black hair tied in a low ponytail, wheatish skin, wearing a mustard yellow cotton kurta, dark blue jeans, and a black office lanyard, standing alone inside a narrow steel apartment lift at night, brushed steel walls, a full-height mirror on the back wall, a glowing red floor display, a flickering white tube light on the ceiling, and half-open sliding metal doors showing a dark fourteenth-floor corridor. Style: Smooth 2D webtoon horror cartoon illustration, uniform black ink outlines, flat cel-shaded colors, 9:16 vertical composition. No text, no captions, no watermark.`
- End every IMG prompt with this exact style lock:
  `Style: Smooth 2D webtoon horror cartoon illustration, uniform black ink outlines, flat cel-shaded colors, 9:16 vertical composition. No text, no captions, no watermark.`

# SECTION C — CHARACTER-SYNCED VIDEO GENERATION PROMPTS (VID-01 TO VID-N)
- Output ONLY the video prompts here, paired 1:1 with IMG-01 to IMG-N (same scene numbers, same phrases, same character counts).
- Duration of each scene = Scene Characters ÷ 11.8, rounded to one decimal (typically 2.0s to 3.5s). Timestamps start at 00.0s and are continuous with no gaps: each scene starts exactly where the previous one ends.
- HARD CEILING: the sum of all Duration values from VID-01 to VID-N, and the end timestamp of the last VID, must be 55.0s or less (target 48.0s to 53.0s).
- Every VID prompt follows RULE 3 (single line, self-contained, English only) and RULE 4 (zero voice, silent lip-sync, physical SFX only).
- End every VID prompt in this order:
  1. This exact style lock: `Style: Smooth 2D webtoon cartoon animation, uniform black ink outlines, flat cel-shaded colors. Smooth human-like character animation with natural eye blinking, pupil movement, lips and jaw open and close in smooth natural silent visual lip-sync motion without any spoken voice, fluid hand actions, and natural walking or running motion. Keep character face, hair, and clothes identical in 9:16 vertical format. No text, no captions, no watermark.`
  2. This exact audio suffix, where the angle-bracket part is replaced by two to four comma-separated physical foley sounds for this scene in English (the angle brackets themselves never appear in the output): `Audio: Generate ONLY these physical background sound effects: <exact English physical foley SFX>. Strictly NO voice generation, NO spoken words, NO narration, NO vocals, and NO AI speech.`
- Full shape example:
  - **VID-01 (Scene 01 · 00.0s–02.4s · Duration: 2.4s · Chars: 28):** `Animate this scene as a 2.4-second vertical 9:16 clip: a young Indian woman, about twenty-four years old, oval face, large worried dark brown eyes, long straight black hair tied in a low ponytail, wheatish skin, wearing a mustard yellow cotton kurta, dark blue jeans, and a black office lanyard, stands alone inside a narrow steel apartment lift at night, with brushed steel walls, a full-height mirror on the back wall, a glowing red floor display, a flickering white tube light on the ceiling, and half-open sliding metal doors showing a dark fourteenth-floor corridor. She slowly lifts her phone with her right hand, steps half a step back from the doors, and turns her head toward the mirror; her eyes blink twice and her pupils dart toward the dark corridor; her lips and jaw open and close in smooth natural silent visual lip-sync motion without any spoken voice. Slow camera push-in. Style: Smooth 2D webtoon cartoon animation, uniform black ink outlines, flat cel-shaded colors. Smooth human-like character animation with natural eye blinking, pupil movement, lips and jaw open and close in smooth natural silent visual lip-sync motion without any spoken voice, fluid hand actions, and natural walking or running motion. Keep character face, hair, and clothes identical in 9:16 vertical format. No text, no captions, no watermark. Audio: Generate ONLY these physical background sound effects: Lift Door Metal Slide, Flickering Tube Light Buzz, Low Heartbeat Thump. Strictly NO voice generation, NO spoken words, NO narration, NO vocals, and NO AI speech.`

# SECTION D — COMPLETE YOUTUBE SHORTS SEO & THUMBNAIL SYSTEM
- **D1. 9:16 Shorts Thumbnail Prompt (Vertical Safe-Zone Locked):** one single bullet line that starts with `- **D1 (Thumbnail · 9:16 · 1024x1792):** ` followed by a self-contained English prompt in single backticks that follows RULE 5 and RULE 6, and ends with: `Style: Smooth 2D webtoon horror cartoon illustration, uniform black ink outlines, flat cel-shaded colors, strict vertical 9:16 portrait 1024x1792, all key characters and horror elements inside the central 80% vertical safe-zone. No text, no captions, no watermark.`
- **D1 Overlay Spec (added in the editor, never inside the raw image):** one bullet line giving the Top Yellow Banner text in #FFD400 with a thick black stroke at the top, and a short Roman Hindi hook in #FFFFFF with a thick black stroke at the bottom, both inside the central 80% safe-zone.
- **D2. 3 High-CTR YouTube Shorts Titles:** Hindi + Hinglish, each ending with #shorts #horror #horrorstory.
- **D3. SEO-Optimized Description (vidIQ Structure):** four-line opening hook, a Roman Hindi comment question, a pinned comment line, keyword-rich Hindi paragraphs, and channel tags.
- **D4. 15 Viral Hashtags and 25 Low-Competition vidIQ Keywords/Tags.**

FINAL SELF-CHECK BEFORE YOU FINISH (fix any failure silently; do not print this checklist):
1. All four sections exist; no triple-backtick fences; no square-bracket or angle-bracket characters anywhere.
2. Section A has exactly the 5 header lines plus one paragraph; the script is 550 to 590 characters, has no Persian or Arabic nuqta (only native ड़ and ढ़), has no digits, and has no scene lines or timings.
3. Every IMG and every VID prompt is one bullet line, fully self-contained (full character and full room description), English only inside the backticks.
4. Every VID prompt contains the exact silent lip-sync phrase, zero quote marks or apostrophes, zero banned speech words, and only physical non-vocal SFX.
5. The sum of all VID durations and the last VID end timestamp are 55.0s or less.
6. Every young protagonist in English is "a young Indian woman" or "a young Indian man".
7. D1 states 9:16, 1024x1792, the central 80% vertical safe-zone, and "No text, no captions, no watermark."
8. The story does not reuse anything from "पापा की वीडियो कॉल" or "दादी की चप्पल", and all Markdown is valid: bold markers and backticks are opened and closed on the same line.
```

---

## PART 3: रेडीमेड TOP 10 नए वायरल हॉरर टॉपिक्स (Episode 01 और 02 को छोड़कर)

| रैंक | नया टॉपिक (Hindi + Roman Title) | पीला बैनर टेक्स्ट | 3-सेकंड हुक और आखिरी ट्विस्ट (48–53s पैटर्न, अधिकतम 55s) |
|---|---|---|---|
| **#01 (Episode 03 लॉक)** | **लिफ्ट का आईना** (`Lift ka Aaina`) | `Lift ka Aaina 🪞😱` | रात ग्यारह बजे चौदहवीं मंजिल की लिफ्ट में मेरे साथ एक अंकल चढ़े; फोन की स्क्रीन में मेरे पीछे कोई नहीं था, लेकिन लिफ्ट के आईने में वही अंकल अपनी गर्दन उल्टी घुमाकर मेरे कंधे पर झुके हुए मुस्कुरा रहे थे। |
| **#02 (Episode 04 लॉक)** | **छत पर उल्टे कदम** (`Chhat par Ulte Kadam`) | `Chhat par Ulte Kadam 👣😨` | हर रात ठीक एक बजे ऊपर वाली छत से भारी कदमों और पायल की आवाज आती थी; पापा ने छत का ताला तोड़ा तो धूल पर कदमों के निशान मुँडेर से बाहर हवा में खत्म हो रहे थे, क्योंकि हमारे घर के ऊपर कोई मंजिल थी ही नहीं, और अब वही कदम हमारी सीढ़ियों से नीचे उतर रहे थे। |
| **#03** | **आखिरी मेट्रो का यात्री** (`Aakhri Metro`) | `Aakhri Metro 🚇😱` | रात की आखिरी मेट्रो में सामने बैठी लड़की बार-बार मेरे बगल वाली खाली सीट को घूरकर रो रही थी; अगले स्टेशन पर उतरते ही उसने मैसेज भेजा, "तुम्हारे बगल वाली सीट खाली नहीं है, किसी का कटा हुआ सिर तुम्हारे कंधे पर टिका है।" |
| **#04** | **हॉस्टल का रूम नंबर दो सौ चार** (`Hostel Room 204`) | `Hostel Room 204 🛏️😨` | रात तीन बजे रूममेट ने ऊपर वाले बंक बेड से झाँककर कहा "भाई दरवाजा मत खोलना, बाहर जो खड़ा है वो मेरी ही शक्ल में है"; टॉर्च जलाई तो मेरा रूममेट दरवाजे के बाहर से काँच पीट रहा था और ऊपर बेड पर कोई और मुस्कुरा रहा था। |
| **#05** | **बाथरूम के नल की आवाज** (`Raat Teen Baje ka Nal`) | `Raat Teen Baje ka Nal 🚰😱` | तीन रातों से ठीक तीन बजे बाथरूम का नल अपने आप खुल जाता था; चौथी रात पापा ने कहा नल बंद करने मत जाना, पर दरवाजे की दरार से देखा तो वहाँ नल नहीं, छत से उल्टा लटका साया अपनी उंगलियों से फर्श थपथपा रहा था। |
| **#06** | **पड़ोसी की खिड़की** (`Padosi ki Khidki`) | `Padosi ki Khidki 🪟😨` | सामने वाले फ्लैट की बालकनी से एक बूढ़ी आंटी हर रात इशारा करती थीं कि "अपने परदे बंद कर लो"; आज पुलिस ने उनका दरवाजा तोड़ा तो पता चला वो एक हफ्ते पहले गुजर चुकी थीं, और वो मुझे मेरे ही कमरे में मेरे पीछे खड़े इंसान से बचा रही थीं। |
| **#07** | **अस्पताल का वार्ड नंबर नौ** (`Ward Number 9`) | `Ward Number 9 🏥😨` | नाइट शिफ्ट में नर्स ने कहा "बेड नंबर चार वाले मरीज को चादर ओढ़ा दो, उन्हें ठंड लग रही है"; चादर उठाई तो बेड खाली था, और पीछे खड़े डॉक्टर ने बताया कि उस नर्स की डेड बॉडी तो शाम से मॉर्चरी में रखी है। |
| **#08** | **ट्रेन की ऊपर वाली बर्थ** (`Upar wali Berth`) | `Upar wali Berth 🚆😨` | रात की ट्रेन में सामने की ऊपर वाली बर्थ से एक आदमी पूरी रात बिना पलक झपकाए मुझे घूरता रहा; सुबह टीटी ने बताया कि उस बर्थ का टिकट कभी बुक ही नहीं होता, और तभी मैंने देखा कि वो आदमी अब मेरी ही बर्थ पर मेरे पैरों के पास बैठा था। |
| **#09** | **शादी की एल्बम** (`Shaadi ki Album`) | `Shaadi ki Album 📸😱` | पुरानी शादी की एल्बम की हर फोटो में मेहमानों के पीछे लाल साड़ी वाली एक ही औरत खड़ी थी जिसे घर में कोई नहीं पहचानता था; आखिरी पन्ना पलटा तो उसमें मेरी आज सुबह की सेल्फी चिपकी थी, और उसमें वही औरत मेरे कंधे के पीछे खड़ी थी। |
| **#10** | **आखिरी कॉलेज बस** (`Aakhri College Bus`) | `Aakhri College Bus 🚌😱` | रात की खाली कॉलेज बस में ड्राइवर ने शीशे में देखकर कहा "भाई पीछे मत मुड़ना, सीधे आगे आकर बैठ जाओ"; खिड़की के काँच में देखा तो आखिरी सीट पर मेरे जैसे कपड़ों में एक बिना आँखों वाला आदमी मेरे कंधे को पकड़े बैठा था। |

---

## PART 4: AGENT 4 PARSING CONTRACT (सभी 6 फॉर्मेट सपोर्टेड)

| Source | Format | Status |
|---|---|---|
| New single-pass (Agent 1 / V5 prompt) | `- **VID-01 (Scene 01 · 00.0s–02.4s · Duration: 2.4s · Chars: 28):** ...` | ✅ Parsed (chars → proportional timing + zero-voice foley lock + 55.0s ceiling) |
| Legacy KIRO headings | `### VID-01 — Scene 01 · 00.0s–02.2s (2.2s) · Camera` + `- **Voice Line:** Devanagari line` | ✅ Parsed (chars from Voice Line) |
| Legacy A3 sync table | `\| 01 \| 00.0s–02.2s \| Hindi Voice Line \| ... \|` | ✅ Parsed (fallback) |
| Captions: A2 pop-up table | `\| 01 \| 00.0s \| 00.5s \| **Raat gyarah** \| 01 \|` | ✅ Priority 1 |
| Captions: inline | `**Raat gyarah** (0.0s–0.5s)` | ✅ Priority 2 (junk `Scene NN` text excluded) |
| Captions: none present | — | ✅ Priority 3: auto 1–2 word Roman pop-ups (character-proportional) |

---

## PART 5: PowerShell रन कमांड्स (WO_GALI_AUTOMATION फोल्डर से)

```powershell
cd "C:\AI KHAN\FINAL NEW BEST STORY\WO_GALI_AUTOMATION"
python agent_1_kiro_opus_story_architect.py "STORY 03 लिफ्ट का आईना (Lift ka Aaina)"
python wo_gali_validator.py "STORY_03_ARTIFACT.md"
python agent_2_chatgpt_image_gen.py
python agent_3_flow_1080p_upscaler_downloader.py
python wo_gali_validator.py "STORY_03_ARTIFACT.md" --audio "STORY_03_VIRAJ.mp3"
python agent_4_gemini_brain_analyzer.py
```

Episode 04 के लिए पहली python लाइन में टॉपिक बदलें: `"STORY 04 छत पर उल्टे कदम (Chhat par Ulte Kadam)"`
