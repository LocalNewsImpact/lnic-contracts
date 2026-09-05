"""Deleting a branch is not a reason to run the suite.

pre-push receives one line per ref on stdin -- "<local_ref> <local_sha>
<remote_ref> <remote_sha>" -- and a deletion's local sha is forty zeros.
The hook never read them, so `git push origin --delete <branch>`, which
pushes no commits at all, ran `make check` first.

The crawler, datadesk and the Source Directory all skip it. This is the
same fix in the same shape, and these tests run the installed hook in a
scratch repository rather than reading it.
"""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts/setup-hooks.sh"

ZERO = "0" * 40
A_COMMIT = "1" * 40
PUSHING = f"refs/heads/topic {A_COMMIT} refs/heads/topic {ZERO}\n"
DELETING = f"(delete) {ZERO} refs/heads/topic {A_COMMIT}\n"


def _run(command, cwd, env=None, stdin=None):
    # Git exports GIT_DIR to a hook run from a linked worktree; with it
    # inherited, the scratch `git init` below re-initialises the pushing
    # repository instead.
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        shell=True,
        capture_output=True,
        text=True,
        input=stdin,
        env={**clean, **(env or {})},
    )


def _install_into(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run("git init -q && git config user.email t@e && git config user.name t", repo)
    (repo / "scripts").mkdir()
    shutil.copy(INSTALLER, repo / "scripts" / "setup-hooks.sh")
    os.chmod(repo / "scripts" / "setup-hooks.sh", 0o755)
    result = _run("./scripts/setup-hooks.sh", repo)
    assert result.returncode == 0, result.stderr
    return repo / ".git" / "hooks" / "pre-push"


def _fake_make(repo, exit_code):
    """A `make` on PATH that records its arguments and exits as told."""
    binn = repo / "fakebin"
    binn.mkdir(exist_ok=True)
    make = binn / "make"
    make.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "make called with: $*" >> "{repo}/make.log"\n'
        f"exit {exit_code}\n"
    )
    os.chmod(make, 0o755)
    return {"PATH": f"{binn}:{os.environ['PATH']}"}


def test_the_installer_is_valid_shell():
    assert _run(f"bash -n {INSTALLER}", ROOT).returncode == 0


def test_the_installed_hook_is_valid_shell(tmp_path):
    hook = _install_into(tmp_path)
    assert _run(f"bash -n {hook}", tmp_path).returncode == 0


def test_the_hook_runs_make_check(tmp_path):
    hook = _install_into(tmp_path)
    repo = hook.parent.parent.parent
    env = _fake_make(repo, 0)
    result = _run(str(hook), repo, env, stdin=PUSHING)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "make called with: check" in (repo / "make.log").read_text()


def test_the_hook_refuses_the_push_when_checks_fail(tmp_path):
    """A hook that reports failure and exits 0 is worse than no hook,
    because it is trusted."""
    hook = _install_into(tmp_path)
    repo = hook.parent.parent.parent
    env = _fake_make(repo, 1)
    result = _run(str(hook), repo, env, stdin=PUSHING)
    assert result.returncode == 1


def test_a_branch_deletion_runs_nothing(tmp_path):
    hook = _install_into(tmp_path)
    repo = hook.parent.parent.parent
    env = _fake_make(repo, 1)  # would refuse the push, if it ran at all
    result = _run(str(hook), repo, env, stdin=DELETING)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (repo / "make.log").exists(), "make ran for a deletion"


def test_a_push_that_also_deletes_still_runs_the_checks(tmp_path):
    hook = _install_into(tmp_path)
    repo = hook.parent.parent.parent
    env = _fake_make(repo, 1)
    result = _run(str(hook), repo, env, stdin=DELETING + PUSHING)
    assert result.returncode == 1
    assert "make called with: check" in (repo / "make.log").read_text()


def test_an_empty_stdin_is_not_a_way_past_the_checks(tmp_path):
    """Run by hand there are no refspecs. An empty read has to mean
    "check": the skip is for what git tells us, not for silence."""
    hook = _install_into(tmp_path)
    repo = hook.parent.parent.parent
    env = _fake_make(repo, 1)
    result = _run(str(hook), repo, env, stdin="")
    assert result.returncode == 1
    assert "make called with: check" in (repo / "make.log").read_text()
