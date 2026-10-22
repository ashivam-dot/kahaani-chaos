"""AI paintings for each beat with Apache-2.0 open weights, run by stable-diffusion.cpp on the runner's CPU.

Z-Image-Turbo (Alibaba Tongyi-MAI, Apache-2.0) Q4_K with its Qwen3-4B text encoder (Apache-2.0) and the
FLUX.1-schnell VAE (Apache-2.0), 576x1024 in 4 steps: 11-20 minutes a picture on a free 4-vCPU runner (measured
October 2026). Standard library only, so the paint jobs need no Python environment.

python -m kahaani.imagegen fetch --root DIR
python -m kahaani.imagegen beats --prompts art-plan.json --only 0,3 --out DIR --root DIR [--alternates 2 --budget 60]

With --alternates N, a beat whose plan lists spare seeds (a cast shot) is repainted with up to N of them after its
main painting, as beatNN-altK.png, while the job's --budget minutes still leave room for one more painting; the
render step falls back on them when the vision check refuses the main one.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

SD_TAG = "master-959-d637cfb"
SD_ZIP = "sd-master-d637cfb-bin-Linux-Ubuntu-24.04-x86_64.zip"
SD_URL = f"https://github.com/leejet/stable-diffusion.cpp/releases/download/{SD_TAG}/{SD_ZIP}"
HF = "https://huggingface.co/{repo}/resolve/main/{file}"
MODELS = {
    "zimage": {
        "diffusion": ("leejet/Z-Image-Turbo-GGUF", "z_image_turbo-Q4_K.gguf"),
        "llm": ("unsloth/Qwen3-4B-Instruct-2507-GGUF", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"),
        "vae": ("Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors"),
        "steps": 4,
    },
}
WIDTH, HEIGHT = 576, 1024
USER_AGENT = "KahaaniChaos/1.0 (github.com/ashivam-dot/kahaani-chaos)"


def _download(url: str, target: Path, attempts: int = 4) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as resp, partial.open("wb") as fh:
                shutil.copyfileobj(resp, fh, 8 << 20)
            partial.replace(target)
            return
        except OSError as err:
            if attempt == attempts - 1:
                raise RuntimeError(f"download failed: {url}: {err}") from err
            time.sleep(10 * (attempt + 1))


def weights(model: str, root: Path) -> dict[str, Path]:
    """The model's three files under root/weights, downloaded once (a finished file is never fetched again)."""
    spec = MODELS[model]
    paths = {}
    for part in ("diffusion", "llm", "vae"):
        repo, name = spec[part]
        path = root / "weights" / repo.replace("/", "--") / Path(name).name
        if not path.exists():
            _download(HF.format(repo=repo, file=name), path)
        paths[part] = path
    return paths


def binary(root: Path) -> Path:
    """The pinned stable-diffusion.cpp CPU build for Ubuntu 24.04, unpacked under root/sd, unless SD_BIN names a
    binary built on the runner."""
    if os.environ.get("SD_BIN"):
        return Path(os.environ["SD_BIN"])
    folder = root / "sd" / SD_TAG
    found = [p for p in folder.rglob("*") if p.is_file() and p.name in ("sd-cli", "sd")] if folder.exists() else []
    if not found:
        archive = root / "sd" / SD_ZIP
        _download(SD_URL, archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(folder)
        archive.unlink()
        found = [p for p in folder.rglob("*") if p.is_file() and p.name in ("sd-cli", "sd")]
    if not found:
        raise RuntimeError(f"no sd-cli in {SD_ZIP}")
    exe = sorted(found, key=lambda p: p.name != "sd-cli")[0]
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


def generate(prompt: str, out: Path, *, model: str = "zimage", root: Path, seed: int = 7, steps: int | None = None,
             width: int = WIDTH, height: int = HEIGHT, threads: int | None = None, timeout: float = 3000) -> dict:
    """One PNG at out; returns timings. Raises RuntimeError when stable-diffusion.cpp fails or writes nothing."""
    exe, paths = binary(root), weights(model, root)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), "--diffusion-model", str(paths["diffusion"]), "--vae", str(paths["vae"]),
           "--llm", str(paths["llm"]), "-p", prompt, "--cfg-scale", "1.0",
           "--steps", str(steps or MODELS[model]["steps"]), "-W", str(width), "-H", str(height),
           "-s", str(seed), "-t", str(threads or os.cpu_count() or 4), "--diffusion-fa", "-o", str(out)]
    verbose = os.environ.get("SD_VERBOSE") == "1"
    if verbose:
        cmd.append("-v")
    env = dict(os.environ, LD_LIBRARY_PATH=f"{exe.parent}:{os.environ.get('LD_LIBRARY_PATH', '')}")
    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    seconds = time.monotonic() - started
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 10_000:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        raise RuntimeError(f"stable-diffusion.cpp failed ({proc.returncode}): {tail}")
    return {"seconds": round(seconds, 1), "model": model, "steps": steps or MODELS[model]["steps"],
            "width": width, "height": height, "seed": seed, "log_tail": (proc.stdout or "")[-600:],
            **({"log_head": (proc.stdout or "")[:3000]} if verbose else {})}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kahaani.imagegen")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="download the binary and one model's weights")
    fetch.add_argument("--model", default="zimage", choices=sorted(MODELS))
    fetch.add_argument("--root", type=Path, required=True)
    beats = sub.add_parser("beats", help="paint the listed beats of a prompts file")
    beats.add_argument("--prompts", type=Path, required=True)
    beats.add_argument("--only", default="", help="comma-separated beat numbers (0-based); empty means all")
    beats.add_argument("--out", type=Path, required=True)
    beats.add_argument("--root", type=Path, required=True)
    beats.add_argument("--model", default="")
    beats.add_argument("--steps", type=int, default=0)
    beats.add_argument("--width", type=int, default=0)
    beats.add_argument("--height", type=int, default=0)
    beats.add_argument("--alternates", type=int, default=0, help="repaints per cast shot, from the plan's spare seeds")
    beats.add_argument("--budget", type=float, default=0, help="minutes this job may spend; 0 means no limit")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        started = time.monotonic()
        binary(args.root)
        weights(args.model, args.root)
        print(json.dumps({"fetched": args.model, "seconds": round(time.monotonic() - started, 1)}))
        return 0
    plan = json.loads(args.prompts.read_text(encoding="utf-8"))
    wanted = {int(x) for x in args.only.split(",") if x.strip()} or set(range(len(plan["beats"])))
    model = args.model or plan.get("model", "zimage")
    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    started = time.monotonic()
    for i, beat in enumerate(plan["beats"]):
        if i not in wanted or not beat.get("prompt"):
            continue
        seeds = [(0, int(beat.get("seed", 7 + i)))] + [(k, int(x)) for k, x in
                                                       enumerate(beat.get("alternates") or [], 1)][:args.alternates]
        last = 0.0
        for alt, seed in seeds:
            elapsed = time.monotonic() - started
            if alt and args.budget and elapsed + 1.15 * last > args.budget * 60:
                print(json.dumps({"beat": i, "alt": alt, "skipped": "out of time budget"}), flush=True)
                break
            stem = f"beat{i:02d}" + (f"-alt{alt}" if alt else "")
            try:
                timing = generate(beat["prompt"], args.out / f"{stem}.png", model=model, root=args.root, seed=seed,
                                  steps=args.steps or plan.get("steps"), width=args.width or plan.get("width", WIDTH),
                                  height=args.height or plan.get("height", HEIGHT))
            except (RuntimeError, subprocess.TimeoutExpired) as err:
                if not alt:
                    failed += 1
                print(json.dumps({"beat": i, "alt": alt, "error": str(err)[-800:]}), flush=True)
                if not alt:
                    break
                continue
            last = timing["seconds"]
            (args.out / f"{stem}.json").write_text(json.dumps({"story": plan.get("story", ""), "beat": i, "alt": alt,
                                                               "prompt": beat["prompt"], **timing},
                                                              ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps({"beat": i, "alt": alt, "seconds": timing["seconds"], "model": model}), flush=True)
    return 1 if failed and failed == len(wanted) else 0


if __name__ == "__main__":
    sys.exit(main())
