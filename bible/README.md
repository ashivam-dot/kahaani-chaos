# Series bible: सन्नाटपुर की रातें

This is the single source of truth for the channel's world, cast and rules. It follows
`kahaani-recreate-2026-10-22/design/PLAN.md` §3, with the deviations listed below.

| File | What it holds |
|---|---|
| `world.yaml` | Sannatpur in 1996: the era and its textures, the house look, 15 places (with spots and image tokens), and `never_exists`, covering religious places, people and acts, banned beings, the real world, brands and the generic words used instead, portrayal rules, and words that never go in titles |
| `cast.yaml` | Jhabbu, Prabhat at 17, Prabhat at 47 (the narrator), Nuzhat and Shailesh. Each has age, role, props and colours (English image tokens plus Hindi), a suggested Gemini voice, speech style and 3 sample lines. Minor people are listed by role only |
| `canon.json` | Niyam N01-N30 with ids (N01-N21 from F1, N22-N30 from the season), facts F01-F12, the thread उल्टी परछाईं (behaviour, truth, payoff in raat-09) and the sign-off |
| `micro_bank.json` | 40 F1 micro-story seeds (e01-e40). Object, anomaly and location are unique across entries; endings rotate; the hook is 10 words or fewer; titles are 40-75 chars with one emoji and use skeletons S1/S2/S3. e28, e33 and e36 carry the thread and should be scheduled before #09 |
| `season1_outline.md` | 9 long-form (F3) loglines, #01-#09. The thread shows up in #03 and #06 and pays off in #09 |
| `name_checks.md` | The YouTube name check for every new proper name: criterion, passed, rejected, and all 304 queries |

## Deviations from PLAN.md (read before touching code or prompts)

- **Narrator अंशु → प्रभात (Prabhat).** अंशु failed the name check.
- **Female lead शबनम → नुज़हत (Nuzhat).** शबनम failed. The first replacement, ज़रीना, also failed (Mirzapur and Disney characters).
- **Comic friend मोंटी → शैलेश (Shailesh).** मोंटी is a Taarak Mehta Ka Ooltah Chashmah character.
  Shailesh is flagged because the real comic poet and actor Shailesh Lodha shares the name. Re-check it before any F3 dialogue is recorded.
- As of this commit, nothing outside `bible/` hardcodes अंशु, शबनम, मोंटी or ज़रीना. Any future code, prompt or
  fixture must use the names above.
- The bible lives in this repo. There was no approval PR gate.
