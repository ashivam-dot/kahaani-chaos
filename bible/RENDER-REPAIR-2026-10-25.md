# Complete closing frames

Preview `40127450982` fixed the duplicated Jhabbu: all seven base paintings passed the actual Gemini
picture editor, including the single seated man in the new ending. Prop identity was 1.0. The measured
voice checks passed the publishing gate; the soundtrack was -14.3 LUFS with -1.4 dBTP true peak.

Release correctly held because the encoded MP4 contained 1,245 frames while the renderer generated
1,249. The raw frame stream and finite padded soundtrack were muxed with `-shortest`, which can stop
before buffered video frames are flushed. The encoder now writes the complete calculated frame count
without that premature-stop option. The existing frame-count gate stays unchanged.

The regression renders a duration between frame boundaries and counts all 163 encoded frames, rather
than only asserting the intended frame count. All 356 tests pass.

The repaired ending's exact CPU-cloud base/alternate paintings and metadata are retained beside the
other thirteen original paintings in `.github/replay/sannatpur-radio-e02-repair/art/`. Source run and
image hashes are explicit. The replacement plan reuses all seven beats and requests zero painter jobs.
Current picture, narration, sound and render checks run again; the same script and narrator identity
remain. The new complete MP4 still needs its own full audiovisual approval before publishing.
