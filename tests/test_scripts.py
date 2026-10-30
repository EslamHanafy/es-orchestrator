#!/usr/bin/env python3
"""Smoke and regression tests for the es-orchestrator scripts and gate templates (standard library only).

Run: python3 -m unittest discover -s tests -v
Every test builds a throw-away git repo in a temp folder; nothing outside it is touched.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS, TEMPLATES = SKILL / "scripts", SKILL / "templates"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}


def run(cmd, cwd=None, env=None, **kw):
    """Run a command and return the CompletedProcess (text mode, never raises)."""
    return subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, env=env or ENV, **kw)


def script(name, *args, cwd=None):
    """Run one of the skill's scripts with the current interpreter."""
    return run([sys.executable, SCRIPTS / name, *args], cwd=cwd)


def git(repo, *args):
    """Run git in `repo`."""
    return run(["git", "-C", repo, *args])


def answers(plan_id="DEMO_PLAN", **extra):
    """A complete, valid answers.json for the demo repo."""
    base = {"PROJECT_NAME": "Demo", "PLAN_ID": plan_id, "PLAN_TITLE": "Demo plan", "PROFILES": ["generic"],
            "PLAN_FILE": "docs/plan.md", "RULES_FILES": "none", "CONTRACT_DOCS": "none", "BASE_BRANCH": "main",
            "WORK_BRANCH": "main", "SOURCE_DIRS": "src", "TEST_DIRS": "tests", "BUILD_CMD": "none", "LINT_CMD": "none",
            "TEST_CMD": "none", "E2E_CMD": "none", "LIVE_CHECK": "none", "LANGUAGES": "EN", "LOCALE_FILES": "none",
            "REVIEWER_MODEL": "opus", "REVIEWER_EFFORT": "medium", "REVIEWER_AGENT": "demo-reviewer",
            "HELPER_MODEL": "sonnet", "BATCH_MINUTES": 30, "STAGE_PATHS": "src docs", "NEVER_STAGE": ".env",
            "FORBIDDEN_GIT": "stash", "OWNER_NAME": "the owner", "LANES": [], "OWNER_RESERVED": ["scope"],
            "CODING_RULES": {"mode": "default"}, "FN_MAX_LINES": 60}
    base.update(extra)
    return base


class Repo:
    """A temp git repo (repo/), with helpers; its sibling repo.worktrees/ is removed with it."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="es-test-"))
        self.path = self.tmp / "repo"
        (self.path / "src").mkdir(parents=True)
        (self.path / "docs").mkdir()
        git(self.path, "init", "-q", "-b", "main")
        (self.path / ".gitignore").write_text(".superpowers/\n.env\n")
        (self.path / "src" / "a.js").write_text("a\n")
        (self.path / "src" / "b.js").write_text("b\n")
        (self.path / "docs" / "plan.md").write_text("# Plan\n### Task 1.1 One\n**Status:** pending\n- [ ] s1\n- [ ] s2\n"
                                                    "### Task 1.2 Two [L]\n**Status:** ✅ done\n- [x] s1\n")
        self.commit("init")

    def commit(self, message):
        """Stage everything and commit."""
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", message)

    def scaffold(self, **extra):
        """Write answers.json and run scaffold.py; returns (CompletedProcess, plan folder)."""
        data = answers(**extra)
        (self.tmp / "answers.json").write_text(json.dumps(data))
        out = script("scaffold.py", "--answers", self.tmp / "answers.json", "--repo", self.path)
        return out, self.path / ".superpowers" / "sdd" / data["PLAN_ID"]

    def cleanup(self):
        """Remove the repo, its worktrees and the temp folder."""
        shutil.rmtree(self.tmp, ignore_errors=True)


class Base(unittest.TestCase):
    """Creates a fresh Repo per test."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.root = self.repo.path


class SkillMetadata(unittest.TestCase):
    """The skills CLI must be able to parse SKILL.md."""

    def test_frontmatter_is_cli_safe(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        self.assertRegex(front, r"(?m)^name: es-orchestrator$")
        self.assertRegex(front, r"(?m)^description: >-$", "description must be a block scalar (it contains ': ')")

    def test_no_hardcoded_install_path(self):
        for f in list(SKILL.glob("references/*.md")) + [SKILL / "SKILL.md"]:
            text = f.read_text(encoding="utf-8")
            hits = [l for l in text.splitlines() if re.search(r"python3 ~/\.claude/skills/es-orchestrator", l)]
            self.assertEqual(hits, [], f"{f.name} hard-codes the install path")


class StatusTests(Base):
    """status.py counting, run classification and stage marker."""

    def setUp(self):
        super().setUp()
        _, self.plan = self.repo.scaffold()

    def status(self, *extra):
        return script("status.py", "--repo", self.root, "--plan-id", "DEMO_PLAN", *extra)

    def test_tasks_not_double_counted(self):
        out = json.loads(self.status("--json").stdout)
        self.assertEqual((out["tasks_done"], out["tasks_total"]), (1, 2))
        self.assertEqual(out["pct_count"], 50)
        self.assertEqual(out["pct_effort"], 80)  # task weights 1 and 4

    def test_heading_without_status_uses_checkboxes(self):
        (self.root / "docs" / "plan.md").write_text("- [ ] loose outside any task\n### Task 1 A\n- [x] a\n- [x] b\n### Task 2 B\n- [x] a\n- [ ] b\n")
        out = json.loads(self.status("--json").stdout)
        self.assertEqual((out["tasks_done"], out["tasks_total"]), (1, 3))

    def test_run_ids_match_exactly(self):
        for run_id in ("B1", "B10"):
            (self.plan / "runs" / run_id).mkdir(parents=True)
            (self.plan / "runs" / run_id / "START").touch()
            (self.plan / "runs" / run_id / "result.json").write_text("{}")
        (self.plan / "B10-review-report.md").write_text("r")
        out = json.loads(self.status("--json").stdout)
        self.assertEqual(out["awaiting_review"], ["B1"])
        self.assertEqual(out["awaiting_owner_report"], ["B10"])
        (self.plan / "B10-OWNER_REPORT_SENT").touch()
        self.assertEqual(json.loads(self.status("--json").stdout)["awaiting_owner_report"], [])

    def test_stale_and_running(self):
        for run_id, age in (("R1", 0), ("R2", 10 * 3600)):
            (self.plan / "runs" / run_id).mkdir(parents=True)
            start = self.plan / "runs" / run_id / "START"
            start.touch()
            os.utime(start, (start.stat().st_atime - age, start.stat().st_mtime - age))
        out = json.loads(self.status("--json").stdout)
        self.assertEqual(out["running"], ["R1"])
        self.assertTrue(out["stale"][0].startswith("R2"))

    def test_stage_marker(self):
        self.assertEqual(self.status("--set-stage", "PLANNED", "--next-mode", "orchestrate B1+B2").returncode, 0)
        self.assertIn("STAGE: PLANNED", self.status().stdout)
        self.assertNotEqual(self.status("--set-stage", "BOGUS").returncode, 0)

    def test_missing_plan_line_is_a_clear_error(self):
        handoff = self.plan / "ORCHESTRATOR_HANDOFF.md"
        handoff.write_text(handoff.read_text().replace("Plan: `", "Planx: `"))
        out = self.status()
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn("Traceback", out.stderr)


class ScaffoldTests(Base):
    """scaffold.py validation and output."""

    def test_generates_plan_folder(self):
        out, plan = self.repo.scaffold()
        self.assertEqual(out.returncode, 0, out.stderr)
        for name in ("ORCHESTRATOR_HANDOFF.md", "check.sh", "run_timeout.py", "scan_added.py", "secret-patterns.txt", "config.json"):
            self.assertTrue((plan / name).exists(), name)
        self.assertTrue(os.access(plan / "check.sh", os.X_OK))

    def test_rejects_bad_plan_id(self):
        out, _ = self.repo.scaffold(plan_id="../../evil")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("PLAN_ID", out.stderr)
        self.assertFalse((self.root / "evil").exists())

    def test_warns_about_unknown_keys(self):
        out, _ = self.repo.scaffold(BUILD_COMMAND="x")
        self.assertIn("UNKNOWN KEY (ignored): BUILD_COMMAND — did you mean BUILD_CMD?", out.stdout)

    def test_only_unknown_file_is_an_error(self):
        _, _ = self.repo.scaffold()
        out = script("scaffold.py", "--answers", self.repo.tmp / "answers.json", "--repo", self.root, "--only", "nope.md")
        self.assertNotEqual(out.returncode, 0)

    def test_refuses_to_overwrite(self):
        self.repo.scaffold()
        out, _ = self.repo.scaffold()
        self.assertNotEqual(out.returncode, 0)

    def test_upgrade_static_adds_missing_helper(self):
        _, plan = self.repo.scaffold()
        (plan / "scan_added.py").unlink()
        out = script("scaffold.py", "--upgrade-static", "--repo", self.root, "--plan-id", "DEMO_PLAN")
        self.assertIn("added: scan_added.py", out.stdout)

    def test_reviewer_agent_scope(self):
        out, _ = self.repo.scaffold()
        self.assertIn(".claude/agents/demo-reviewer.md", out.stdout)
        self.assertNotIn(str(Path.home() / ".claude" / "agents"), out.stdout)


class ArchiveTests(Base):
    """archive.py on a generated handoff and on a broken one."""

    def test_dry_run_on_generated_plan(self):
        _, plan = self.repo.scaffold()
        out = script("archive.py", "--repo", self.root, "--plan-id", "DEMO_PLAN", "--session", "3")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_missing_live_heading_is_a_clear_error(self):
        _, plan = self.repo.scaffold()
        (plan / "ORCHESTRATOR_HANDOFF.md").write_text("# nothing\n")
        out = script("archive.py", "--repo", self.root, "--plan-id", "DEMO_PLAN", "--session", "3")
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn("Traceback", out.stderr)


class DetectTests(unittest.TestCase):
    """detect_stack.py classification and the quick-setup draft."""

    def detect(self, root, *extra):
        out = script("detect_stack.py", root, *extra)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_xcode_project_is_mobile(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ios" / "App.xcodeproj").mkdir(parents=True)
            stacks = self.detect(tmp)["stacks"]
            self.assertEqual([(s["profile"], s["tool"]) for s in stacks], [("mobile", "swift")])

    def test_plain_dart_package_is_not_mobile(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pubspec.yaml").write_text("name: x\nenvironment:\n  sdk: ^3.0.0\n")
            self.assertEqual(self.detect(tmp)["PROFILES"], ["generic"])

    def test_flutter_app_is_mobile(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pubspec.yaml").write_text("name: x\ndependencies:\n  flutter:\n    sdk: flutter\n")
            info = self.detect(tmp)
            self.assertEqual(info["PROFILES"], ["mobile"])
            self.assertEqual(info["stacks"][0]["commands"]["WORKTREE_SETUP_CMD"], "flutter pub get")

    def test_plan_candidate_found_by_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "docs" / "plans").mkdir(parents=True)
            (Path(tmp) / "docs" / "plans" / "p.md").write_text("x")
            self.assertEqual(self.detect(tmp)["plan_candidates"], ["docs/plans/p.md"])

    def test_draft_answers_scaffolds_cleanly(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        (repo.path / "package.json").write_text('{"dependencies":{"express":"1"},"scripts":{"build":"true"}}')
        draft = json.loads(script("detect_stack.py", repo.path, "--draft-answers").stdout)
        self.assertRegex(draft["PLAN_ID"], r"^[A-Z][A-Z0-9_]+$")
        (repo.tmp / "d.json").write_text(json.dumps(draft))
        out = script("scaffold.py", "--answers", repo.tmp / "d.json", "--repo", repo.path)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("UNKNOWN KEY", out.stdout)


class WorktreeBase(Base):
    """Shared setup for the parallel-pair tests: a scaffolded plan with a setup command and a copied file."""

    def setUp(self):
        super().setUp()
        _, self.plan = self.repo.scaffold(WORKTREE_SETUP_CMD="echo ok > .setup-done", WORKTREE_COPY_FILES=[".env"])
        (self.root / ".env").write_text("K=1\n")
        self.wt = self.repo.tmp / "repo.worktrees" / "DEMO_PLAN"

    def w(self, *args):
        return script("worktree.py", *args[:1], "--repo", self.root, "--plan-id", "DEMO_PLAN", *args[1:])

    def add_both(self):
        out = self.w("add", "--id", "A", "--id", "B")
        self.assertEqual(out.returncode, 0, out.stderr)

    def work(self, batch, filename, text, gate=True):
        (self.wt / batch / filename).write_text(text)
        if gate:
            (self.plan / "runs" / batch / "gate.log").write_text("ALL GATES PASS\n")



class WorktreeTests(WorktreeBase):
    """The parallel-pair flow: add → snapshot → land → remove, and every refusal."""

    def test_full_flow(self):
        self.add_both()
        self.assertEqual((self.wt / "A" / ".env").read_text(), "K=1\n")
        self.assertTrue((self.wt / "A" / ".setup-done").exists())
        (self.wt / "B" / "src" / "new.js").write_text("n\n")
        self.work("A", "src/a.js", "a2\n")
        self.work("B", "src/b.js", "b2\n")
        for batch in "AB":
            self.assertEqual(self.w("snapshot", "--id", batch).returncode, 0)
        files_b = (self.plan / "runs" / "B" / "files.txt").read_text().split()
        self.assertEqual(sorted(files_b), ["src/b.js", "src/new.js"])  # setup output and copied .env excluded
        out = self.w("land", "--id", "A", "--id", "B")
        self.assertEqual(out.returncode, 0, out.stderr)
        status = git(self.root, "status", "--porcelain").stdout
        self.assertIn("M src/a.js", status)
        self.assertIn("?? src/new.js", status)
        self.assertEqual(self.w("remove", "--all").returncode, 0)
        self.assertFalse((self.wt / "A").exists())
        self.assertNotIn("es/demo_plan", git(self.root, "branch").stdout)

    def test_add_refuses_dirty_tree(self):
        (self.root / "src" / "a.js").write_text("dirty\n")
        self.assertEqual(self.w("add", "--id", "A").returncode, 2)

    def test_land_refuses_overlap(self):
        self.add_both()
        self.work("A", "src/a.js", "x\n")
        self.work("B", "src/a.js", "y\n")
        for batch in "AB":
            self.w("snapshot", "--id", batch)
        out = self.w("land", "--id", "A", "--id", "B")
        self.assertEqual(out.returncode, 2)
        self.assertIn("not disjoint", out.stderr)
        self.assertEqual(git(self.root, "status", "--porcelain").stdout.strip(), "")

    def test_land_refuses_stale_gate_evidence(self):
        self.add_both()
        self.work("A", "src/a.js", "x\n")
        gate = self.plan / "runs" / "A" / "gate.log"
        os.utime(gate, (gate.stat().st_atime - 100, gate.stat().st_mtime - 100))
        self.assertEqual(self.w("snapshot", "--id", "A").returncode, 0)
        self.assertEqual(self.w("land", "--id", "A").returncode, 4)
        self.assertEqual(self.w("land", "--id", "A", "--allow-stale").returncode, 0)

    def test_land_refuses_moved_head(self):
        self.add_both()
        self.work("A", "src/a.js", "x\n")
        self.w("snapshot", "--id", "A")
        (self.root / "docs" / "other.md").write_text("o\n")
        self.repo.commit("moved")
        out = self.w("land", "--id", "A")
        self.assertEqual(out.returncode, 2)
        self.assertIn("moved", out.stderr)

    def test_remove_refuses_unlanded_without_force(self):
        self.add_both()
        self.assertEqual(self.w("remove", "--id", "A").returncode, 2)
        self.assertEqual(self.w("remove", "--id", "A", "--force").returncode, 0)

    def test_bad_batch_id_rejected(self):
        self.assertEqual(self.w("add", "--id", "../x").returncode, 2)


class LocaleParityTests(unittest.TestCase):
    """locale_parity.py keys, empties, placeholders and formats."""

    def check(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in files.items():
                (Path(tmp) / name).write_text(text, encoding="utf-8")
                paths.append(str(Path(tmp) / name))
            return run([sys.executable, TEMPLATES / "locale_parity.py", ",".join(paths)])

    def test_parity_ok(self):
        self.assertEqual(self.check({"en.json": '{"a":"Hi {name}"}', "ar.json": '{"a":"مرحبا {name}"}'}).returncode, 0)

    def test_missing_and_empty(self):
        out = self.check({"en.json": '{"a":"x","b":"y"}', "ar.json": '{"a":""}'})
        self.assertEqual(out.returncode, 1)
        self.assertIn("missing b", out.stdout)
        self.assertIn("empty a", out.stdout)

    def test_placeholder_mismatch(self):
        out = self.check({"en.json": '{"a":"Hi {name}"}', "ar.json": '{"a":"Hi {user}"}'})
        self.assertEqual(out.returncode, 1)
        self.assertIn("placeholders", out.stdout)

    def test_properties_and_unsupported(self):
        self.assertEqual(self.check({"a.properties": "k=Hello %s\n", "b.properties": "k=Hola %s\n"}).returncode, 0)
        self.assertEqual(self.check({"a.yaml": "k: v\n", "b.yaml": "k: v\n"}).returncode, 2)


class ScanAddedTests(unittest.TestCase):
    """scan_added.py: raw vs code-only rules and the allow list."""

    def scan(self, diff, rules, allow=""):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in (("d.diff", diff), ("r.txt", rules), ("a.txt", allow)):
                (Path(tmp) / name).write_text(text)
            return run([sys.executable, TEMPLATES / "scan_added.py", "--diff", Path(tmp) / "d.diff", "--rules",
                        Path(tmp) / "r.txt", "--allow", Path(tmp) / "a.txt"])

    def test_code_only_rule_ignores_strings_and_comments(self):
        diff = '+++ b/x.dart\n+print("Hello!");\n+// done!\n+final y = x!;\n'
        out = self.scan(diff, "~null-assert|[A-Za-z0-9_\\)\\]]![.;,)[:space:]]\n")
        self.assertEqual(out.returncode, 1)
        self.assertIn("final y = x!;", out.stdout)
        self.assertNotIn("Hello", out.stdout)
        self.assertNotIn("done", out.stdout)

    def test_raw_rule_sees_comments(self):
        out = self.scan("+++ b/x.js\n+// TODO later\n", "todo|TODO|FIXME\n")
        self.assertEqual(out.returncode, 1)

    def test_allow_list(self):
        out = self.scan("+++ b/x.js\n+// TODO later\n", "todo|TODO\n", "x.js|todo|ruled in R-1\n")
        self.assertEqual(out.returncode, 0)

    def test_secret_patterns_file_catches_keys(self):
        out = self.scan("+++ b/c.env\n+KEY=AKIAABCDEFGHIJKLMNOP\n", (TEMPLATES / "secret-patterns.txt").read_text())
        self.assertEqual(out.returncode, 1)


class RunTimeoutTests(unittest.TestCase):
    """run_timeout.py exit codes."""

    def test_passes_exit_code_through(self):
        out = run([sys.executable, TEMPLATES / "run_timeout.py", "5", "--", "bash", "-c", "exit 3"])
        self.assertEqual(out.returncode, 3)

    def test_kills_on_timeout(self):
        out = run([sys.executable, TEMPLATES / "run_timeout.py", "1", "--", "bash", "-c", "sleep 30"])
        self.assertEqual(out.returncode, 124)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class GateTests(Base):
    """check.sh end to end on a scaffolded plan."""

    def gate(self, **extra):
        _, plan = self.repo.scaffold(**extra)
        self.plan = plan
        return lambda: run(["bash", plan / "check.sh", "HEAD", "--no-tests"], cwd=self.root)

    def test_clean_change_passes_and_temp_is_removed(self):
        run_gate = self.gate()
        (self.root / "src" / "a.js").write_text("a changed\n")
        out = run_gate()
        self.assertIn("ALL GATES PASS", out.stdout, out.stdout)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(list(self.plan.glob(".gate-tmp.*")), [])

    def test_forbidden_pattern_fails(self):
        run_gate = self.gate()
        (self.root / "src" / "a.js").write_text("// TODO later\n")
        out = run_gate()
        self.assertEqual(out.returncode, 1)
        self.assertIn("forbidden patterns", out.stdout)

    def test_secret_in_non_source_file_fails(self):
        run_gate = self.gate()
        (self.root / "docs" / "notes.md").write_text("key AKIAABCDEFGHIJKLMNOP\n")
        out = run_gate()
        self.assertEqual(out.returncode, 1)
        self.assertIn("possible secrets", out.stdout)

    def test_hung_command_times_out(self):
        run_gate = self.gate(BUILD_CMD="sleep 30", GATE_TIMEOUT_SECONDS=1)
        (self.root / "src" / "a.js").write_text("changed\n")
        out = run_gate()
        self.assertEqual(out.returncode, 1)
        self.assertIn("TIMED OUT", out.stdout)


class DoctorTests(Base):
    """doctor.py on a healthy and on an incomplete plan."""

    def test_flags_missing_file(self):
        _, plan = self.repo.scaffold()
        (plan / "scan_added.py").unlink()
        out = script("doctor.py", "--repo", self.root, "--plan-id", "DEMO_PLAN")
        self.assertEqual(out.returncode, 1)
        self.assertIn("missing scan_added.py", out.stdout)

    def test_environment_only(self):
        self.assertEqual(script("doctor.py", "--repo", self.root).returncode, 0)


class WorktreeRegressionTests(WorktreeBase):
    """Defects found by the independent review of the worktree flow (each test names the failure it guards)."""

    def snapshot_and_land(self, ids="A", **files):
        for batch, (name, data) in files.items():
            path = self.wt / batch / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            (self.plan / "runs" / batch / "gate.log").write_text("ALL GATES PASS\n")
        for batch in files:
            self.assertEqual(self.w("snapshot", "--id", batch).returncode, 0)

    def test_crlf_and_non_utf8_land_byte_exact(self):
        (self.root / "src" / "latin.txt").write_bytes(b"caf\xe9\r\n")
        (self.root / "src" / "crlf.txt").write_bytes(b"one\r\ntwo\r\n")
        self.repo.commit("legacy files")
        self.add_both()
        (self.wt / "A" / "src" / "latin.txt").write_bytes(b"caf\xe9 changed\r\n")
        (self.wt / "A" / "src" / "crlf.txt").write_bytes(b"one\r\ntwo\r\nthree\r\n")
        self.snapshot_and_land(A=("src/new_crlf.txt", b"n1\r\nn2\r\n"))
        out = self.w("land", "--id", "A")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual((self.root / "src" / "new_crlf.txt").read_bytes(), b"n1\r\nn2\r\n")
        self.assertEqual((self.root / "src" / "latin.txt").read_bytes(), b"caf\xe9 changed\r\n")
        self.assertEqual((self.root / "src" / "crlf.txt").read_bytes(), b"one\r\ntwo\r\nthree\r\n")

    def test_edit_after_snapshot_blocks_land_and_remove(self):
        self.add_both()
        self.snapshot_and_land(A=("src/a.js", b"a2\n"))
        (self.wt / "A" / "src" / "late.js").write_text("late\n")
        out = self.w("land", "--id", "A")
        self.assertEqual(out.returncode, 4)
        self.assertIn("edits after the snapshot", out.stderr)
        (self.plan / "runs" / "A" / "gate.log").write_text("ALL GATES PASS (re-run)\n")  # the implementer re-ran its gate
        self.assertEqual(self.w("snapshot", "--id", "A").returncode, 0)
        self.assertEqual(self.w("land", "--id", "A").returncode, 0)
        (self.wt / "A" / "src" / "later.js").write_text("later\n")
        self.assertEqual(self.w("remove", "--id", "A").returncode, 2)
        self.assertTrue((self.wt / "A").exists())

    def test_readding_an_id_archives_the_old_attempt(self):
        self.add_both()
        self.snapshot_and_land(B=("src/b.js", b"OLD\n"))
        self.assertEqual(self.w("remove", "--id", "B", "--force").returncode, 0)
        self.assertEqual(self.w("add", "--id", "B").returncode, 0)
        run = self.plan / "runs" / "B"
        self.assertFalse((run / "SNAPSHOT.json").exists())
        self.assertTrue(list(run.glob("previous-*/SNAPSHOT.json")))
        self.assertNotEqual(self.w("land", "--id", "B").returncode, 0)  # no snapshot of the new attempt

    def test_remove_all_after_forced_removal(self):
        self.add_both()
        self.snapshot_and_land(A=("src/a.js", b"a2\n"))
        self.assertEqual(self.w("land", "--id", "A").returncode, 0)
        self.assertEqual(self.w("remove", "--id", "B", "--force").returncode, 0)
        self.assertEqual(self.w("remove", "--all").returncode, 0)

    def test_case_only_difference_is_an_overlap(self):
        self.add_both()
        self.snapshot_and_land(A=("src/Foo.js", b"x\n"), B=("src/foo.js", b"y\n"))
        out = self.w("land", "--id", "A", "--id", "B")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(git(self.root, "status", "--porcelain").stdout.strip(), "")

    def test_non_ascii_names_are_checked_for_staleness(self):
        self.add_both()
        name = "src/ملف.js"
        (self.wt / "A" / name).write_text("x\n")
        gate = self.plan / "runs" / "A" / "gate.log"
        gate.write_text("ok\n")
        os.utime(gate, (gate.stat().st_atime - 100, gate.stat().st_mtime - 100))
        self.assertEqual(self.w("snapshot", "--id", "A").returncode, 0)
        files = (self.plan / "runs" / "A" / "files.txt").read_text().split("\n")
        self.assertIn(name, files)
        self.assertEqual(self.w("land", "--id", "A").returncode, 4)  # stale: the file is newer than the gate log

    def test_diff_noprefix_config_does_not_break_land(self):
        git(self.root, "config", "diff.noprefix", "true")
        self.add_both()
        self.snapshot_and_land(A=("src/a.js", b"a2\n"))
        self.assertEqual(self.w("land", "--id", "A").returncode, 0)


class GateRegressionTests(Base):
    """Defects found by the independent review of check.sh and its helpers."""

    def setUp(self):
        super().setUp()
        _, self.plan = self.repo.scaffold()

    def gate(self, cwd=None, env=None):
        return run(["bash", self.plan / "check.sh", "HEAD", "--no-tests"], cwd=cwd or self.root, **({"env": env} if env else {}))

    def test_non_ascii_untracked_file_is_scanned(self):
        (self.root / "src" / "é.js").write_text("// TODO later\nconst k = 'AKIAABCDEFGHIJKLMNOP';\n")
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("forbidden patterns", out.stdout)

    def test_allow_listed_fixture_cannot_hide_the_next_file(self):
        (self.plan / "forbidden-allow.txt").write_text("docs/aaa.md|secret-aws-access-key|fixture\n")
        (self.root / "docs" / "aaa.md").write_bytes(b"k = AKIAABCDEFGHIJKLMNOP")  # no trailing newline
        (self.root / "docs" / "bbb.md").write_text("real AKIAZZZZZZZZZZZZZZZZ\n")
        out = self.gate()
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("docs/bbb.md", out.stdout)

    def test_unquoted_env_secret_is_caught(self):
        (self.root / "docs" / "prod.env").write_text("DB_PASSWORD=hunter2hunter2hunter2xx\n")
        self.assertEqual(self.gate().returncode, 1)

    def test_increment_line_is_scanned(self):
        (self.root / "src" / "a.js").write_text("++counter; // TODO later\n")
        self.assertIn("forbidden patterns", self.gate().stdout)

    def test_broken_snippet_fails_the_gate(self):
        (self.plan / "gates.d").mkdir(exist_ok=True)
        (self.plan / "gates.d" / "bad.sh").write_text("if [[ x ]]; then\n")
        out = self.gate()
        self.assertEqual(out.returncode, 1)
        self.assertIn("syntax error", out.stdout)

    def test_running_inside_a_worktree_without_check_root_is_refused(self):
        wt = self.repo.tmp / "other"
        git(self.root, "worktree", "add", "-q", "-b", "x", wt)
        out = self.gate(cwd=wt)
        self.assertEqual(out.returncode, 2)
        self.assertIn("CHECK_ROOT", out.stdout)
        ok = run(["bash", self.plan / "check.sh", "HEAD", "--no-tests"], cwd=wt, env={**ENV, "CHECK_ROOT": str(wt)})
        self.assertEqual(ok.returncode, 0, ok.stdout)

    def test_all_profile_snippets_parse_under_the_system_bash(self):
        bash = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
        for snippet in sorted(SKILL.glob("profiles/*/gate-snippets/*.sh")):
            out = run([bash, "-n", snippet])
            self.assertEqual(out.returncode, 0, f"{snippet.name}: {out.stderr}")


class SignalTests(unittest.TestCase):
    """run_timeout.py must not leave grandchildren running when it is terminated."""

    def test_sigterm_kills_the_whole_group(self):
        import signal
        import time
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "pid"
            proc = subprocess.Popen([sys.executable, str(TEMPLATES / "run_timeout.py"), "60", "--", "bash", "-c",
                                     f"sleep 300 & echo $! > {pidfile}; wait"])
            for _ in range(50):
                if pidfile.exists() and pidfile.read_text().strip():
                    break
                time.sleep(0.1)
            child = int(pidfile.read_text().strip())
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=20)
            time.sleep(0.3)
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)


class StatusFormatTests(unittest.TestCase):
    """status.plan_tasks() on odd plan formats."""

    def tasks(self, text):
        sys.path.insert(0, str(SCRIPTS))
        import importlib
        status = importlib.import_module("status")
        return [(t[0], t[2]) for t in status.plan_tasks(text.splitlines())]

    def test_plain_words_after_task_are_not_tasks(self):
        self.assertEqual(len(self.tasks("## Task list\n- [x] a\n- [ ] b\n- [ ] c\n")), 3)

    def test_negated_statuses_are_not_done(self):
        for text in ("not done yet", "❌ not complete", "pending (done when tests pass)", "Not started — complete rewrite"):
            self.assertEqual(self.tasks(f"### Task 1: A\nStatus: {text}\n")[0][1], False, text)
        for text in ("✅ done", "**done** (2026-01-01)", "Completed", "✅"):
            self.assertEqual(self.tasks(f"### Task 1: A\n**Status:** {text}\n")[0][1], True, text)

    def test_signal_less_task_counts_as_open(self):
        found = self.tasks("### Task 1: A\n**Status:** done\n### Task 2: B\nprose only\n### Task 3: C\nprose\n")
        self.assertEqual([d for _, d in found], [True, False, False])

    def test_mid_line_status_text_is_ignored(self):
        self.assertEqual(self.tasks("### Task 1: A\nCheck the HTTP status: 200 is done here\n- [ ] x\n")[0][1], False)

    def test_parent_status_wins_over_first_child(self):
        text = "### Task 1: A\n**Status:** pending\n#### Step 1.1 x\nStatus: done\n#### Step 1.2 y\nStatus: pending\n"
        self.assertEqual(self.tasks(text), [("Task 1: A", False)])

    def test_children_count_when_the_parent_has_no_signal(self):
        text = "### Task 1: A\nintro\n#### Step 1.1 x\nStatus: done\n#### Step 1.2 y\nStatus: pending\n"
        self.assertEqual([d for _, d in self.tasks(text)], [True, False])

    def test_fenced_checkboxes_are_ignored(self):
        self.assertEqual(self.tasks("```\n- [ ] example\n```\n- [x] real\n"), [("real", True)])


class StatusLegacyTests(Base):
    """Legacy report names and plans without recognisable tasks."""

    def setUp(self):
        super().setUp()
        _, self.plan = self.repo.scaffold()

    def test_hyphenated_legacy_report_covers_its_runs_exactly(self):
        for run_id in ("B1", "B1K", "B2", "B10"):
            (self.plan / "runs" / run_id).mkdir(parents=True)
            (self.plan / "runs" / run_id / "result.json").write_text("{}")
        (self.plan / "B1-B1K-B2-review-report.md").write_text("r")
        out = json.loads(script("status.py", "--repo", self.root, "--plan-id", "DEMO_PLAN", "--json").stdout)
        self.assertEqual(out["awaiting_review"], ["B10"])

    def test_only_the_newest_report_can_await_the_owner(self):
        for name, age in (("A-review-report.md", 100), ("B-review-report.md", 0)):
            f = self.plan / name
            f.write_text("r")
            os.utime(f, (f.stat().st_atime - age, f.stat().st_mtime - age))
        out = json.loads(script("status.py", "--repo", self.root, "--plan-id", "DEMO_PLAN", "--json").stdout)
        self.assertEqual(out["awaiting_owner_report"], ["B"])

    def test_plan_without_recognisable_tasks_says_so(self):
        (self.root / "docs" / "plan.md").write_text("- B1 (JUDGEMENT) do things\n- B2 more\n")
        out = script("status.py", "--repo", self.root, "--plan-id", "DEMO_PLAN")
        self.assertIn("no tasks recognised", out.stdout)


class LocaleRegressionTests(unittest.TestCase):
    """Positional placeholders and a misconfigured file list."""

    def check(self, arg, files=None):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in (files or {}).items():
                (Path(tmp) / name).write_text(text, encoding="utf-8")
                paths.append(str(Path(tmp) / name))
            return run([sys.executable, TEMPLATES / "locale_parity.py", arg if arg is not None else ",".join(paths)])

    def test_positional_braces_must_match(self):
        out = self.check(None, {"en.json": '{"a":"Hello {}, you have {} items"}', "ar.json": '{"a":"مرحبا {}"}'})
        self.assertEqual(out.returncode, 1)

    def test_empty_file_list_is_an_error_not_a_pass(self):
        self.assertEqual(self.check("").returncode, 2)

    def test_single_file_still_checks_empty_values(self):
        self.assertEqual(self.check(None, {"en.json": '{"a":""}'}).returncode, 1)
        self.assertEqual(self.check(None, {"en.json": '{"a":"x"}'}).returncode, 0)



if __name__ == "__main__":
    unittest.main()
