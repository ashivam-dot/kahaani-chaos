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

The replacement `40132420577` did retain every expected frame (1,229). Its seven pictures and original
voice passed, but the final soundtrack measured -15.1 LUFS, below the unchanged -15 to -13 band. The old
one-pass normalizer estimated loudness before appending the closing silence. Production now measures the
complete finite mix and applies a second normalization pass, with -2 dBTP headroom before AAC encoding.

An explicit `audio_finish` batch intent can recover this exact otherwise passing audio-level hold. It binds
the original MP4, story, timing, picture reports and health by SHA-256; accepts only audio-level failures;
preserves every encoded video packet and frame; retains the narrator and all timing; and measures the new
soundtrack against the existing sound, music-bed and runtime gates. Source reports and bitstream hashes are
archived. Picture/frame/voice or music-balance failures cannot use this path. The complete repaired MP4 needs
a new media-bound audiovisual verdict. No previous approval is inherited.

Local direct verification of the exact held MP4 produced -14.3 LUFS, -1.8 dBTP and a -25.7 LUFS music bed,
with the same video bitstream. Those measurements are diagnostic evidence, not a cloud release approval.
