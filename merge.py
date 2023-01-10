"""Tool to merge cpython pot files to python-docs-tr po files for a
given branch.
"""

import re
import shutil
from pathlib import Path
import argparse
import subprocess
from subprocess import PIPE
from tqdm import tqdm


def run(*args: str | Path, **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command with subprocess.run() with check=True and
    encoding="UTF-8".
    """
    return subprocess.run(list(args), encoding="UTF-8", check=True, **kwargs)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cpython_repo",
        default=Path("cpython/"),
        type=Path,
        help="Use this given cpython clone.",
    )
    parser.add_argument("branch", help="Merge from this branch")
    return parser.parse_args()


def setup_repo(repo_path: Path, branch: str):
    """Ensure we're up-to-date."""
    run("git", "-C", repo_path, "checkout", branch)
    run("git", "-C", repo_path, "pull", "--ff-only")


def copy_new_files(new_files: set[Path], pot_path: Path) -> None:
    """Just copy new po files to our hierarchy."""
    print(f"{len(new_files)} new files.")
    for file in new_files:
        file.parent.mkdir(parents=True, exist_ok=True)
        src = (pot_path / file).with_suffix(".pot")
        run("msgcat", "-o", file, src)


def update_known_files(known_files: set[Path], pot_path: Path) -> None:
    """msgmerge updated pot files in our po files."""
    print(f"{len(known_files)} files to update.")
    for file in tqdm(known_files, desc="merging pot files"):
        src = (pot_path / file).with_suffix(".pot")
        run("msgmerge", "-q", "--backup=off", "--force-po", "-U", file, src)


def remove_old_files(old_files: set[Path]) -> None:
    """Remove files removed upstream."""
    print(f"{len(old_files)} removed files.")

    for file in old_files:
        run("git", "rm", file)


def clean_paths(files: set[Path]) -> None:
    """Ensure the path present in po files are always relative.

    This avoid having diffs on those paths when we change something in
    a script.
    """
    for file in tqdm(files, desc="Cleaning rst path in pot files"):
        contents = file.read_text(encoding="UTF-8")
        contents = re.sub("^#: .*Doc/", "#: ", contents, flags=re.M)
        file.write_text(contents, encoding="UTF-8")


def update_makefile(cpython_repo: Path) -> None:
    """Update CPYTHON_CURRENT_COMMIT in the Makefile.

    So that when we run `make` it use the same commit than the one
    used to generate the `po` files.
    """
    makefile = Path("Makefile").read_text(encoding="UTF-8")
    head = run("git", "-C", cpython_repo, "rev-parse", "HEAD", stdout=PIPE).stdout.strip()
    makefile = re.sub(
        "^CPYTHON_CURRENT_COMMIT :=.*$",
        f"CPYTHON_CURRENT_COMMIT := {head}",
        makefile,
        flags=re.M,
    )
    Path("Makefile").write_text(makefile, encoding="UTF-8")
    run("git", "add", "Makefile")


def main():
    args = parse_args()
    setup_repo(args.cpython_repo, args.branch)
    run(
        *["sphinx-build", "-jauto", "-QDgettext_compact=0", "-bgettext", ".", "../pot"],
        cwd=args.cpython_repo / "Doc",
    )
    pot_path = args.cpython_repo / "pot"
    upstream = {file.relative_to(pot_path).with_suffix(".po") for file in pot_path.glob("**/*.pot")}
    downstream = {Path(po) for po in run("git", "ls-files", "*.po", stdout=PIPE).stdout.splitlines()}
    copy_new_files(upstream - downstream, pot_path=pot_path)
    update_known_files(upstream & downstream, pot_path=pot_path)
    remove_old_files(downstream - upstream)
    clean_paths((upstream - downstream) | (upstream & downstream))
    shutil.rmtree(pot_path)
    run("powrap", "-m")
    update_makefile(args.cpython_repo)


if __name__ == "__main__":
    main()
