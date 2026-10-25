"""Read-only production clone reproduction; no painting, ledger or publishing access."""
import argparse
import json
from pathlib import Path

from kahaani import voice
from kahaani.spec import Story


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    replay = args.replay.resolve()
    if not replay.is_relative_to(root / '.github/replay') or replay.suffix != '.json':
        raise ValueError('Use an existing story inside .github/replay')
    story = Story.load(replay)
    args.out.mkdir(parents=True, exist_ok=True)
    story.save(args.out / 'story.json')
    timing = voice._chatterbox_story(story, args.out)
    problems = voice.problems(timing['voice']['checks'], final=True)
    result = {'premise': story.premise, 'problems': problems,
              'voice': timing['voice'], 'release_approval': False}
    (args.out / 'diagnosis.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return int(bool(problems))


if __name__ == '__main__':
    raise SystemExit(main())
