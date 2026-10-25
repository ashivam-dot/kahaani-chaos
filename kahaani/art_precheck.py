"""Optional early picture check to avoid painting unnecessary spares. Never approves a release."""
import argparse
import hashlib
import json
from pathlib import Path


def check(story_path: Path, image: Path, beat: int) -> dict:
    from . import gemini, look, vision

    if not gemini.available():
        raise RuntimeError('early picture editor unavailable; retain ordinary spare generation')
    story = json.loads(story_path.read_text())
    item = story['beats'][beat]
    plan = look.plan(story['id'], story['beats'], story['cast'])[beat]
    meta = json.loads(image.with_suffix('.json').read_text())
    if meta.get('story') != story['id'] or meta.get('beat') != beat or meta.get('prompt') != plan['prompt']:
        raise ValueError('painting does not match the exact story and planned prompt')
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    cast = '; '.join(look.character(c) for c in story['cast'])
    verdict = vision.judge([(image, item['text'], vision.expected(plan['cast']), item['scene'])],
                           story['title'] + ' — ' + story.get('description', ''), cast, gemini.look)[0]
    reason = vision.rejected(verdict, bool(plan['cast']), beat == 0, item['scene'])
    return {'image_sha256': sha, 'skip_remaining_spares': reason is None, 'reason': reason,
            'verdict': verdict, 'release_approval': False,
            'scope': 'Early spare-generation decision only; independent final picture and audiovisual gates remain'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--story', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--beat', type=int, required=True)
    a = p.parse_args()
    print(json.dumps(check(a.story, a.image, a.beat), ensure_ascii=False))


if __name__ == '__main__':
    main()
