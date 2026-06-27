"""
Skill 系统测试
覆盖 .md skill 文件的加载、解析、发现、触发词匹配。
"""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.agent.skills import (
    load_skill_file, discover_skills, find_skill_by_name,
    find_skill_by_trigger, list_skills, install_skill_template,
    _parse_frontmatter,
)


# ==================== Frontmatter 解析 ====================

class TestParseFrontmatter:

    def test_basic_frontmatter(self):
        content = """---
name: code-review
description: 审查代码
---
body content"""
        fm = _parse_frontmatter(content)
        assert fm.get("name") == "code-review"
        assert fm.get("description") == "审查代码"

    def test_frontmatter_with_list(self):
        content = """---
name: deploy
triggers:
  - 部署
  - deploy
  - 发布
---
body"""
        fm = _parse_frontmatter(content)
        assert "triggers" in fm
        assert isinstance(fm["triggers"], list)
        assert "部署" in fm["triggers"]
        assert "deploy" in fm["triggers"]
        assert "发布" in fm["triggers"]

    def test_frontmatter_with_multiline_string(self):
        content = """---
name: complex
description: complex skill
steps: |
  1. step one
  2. step two
---
body"""
        fm = _parse_frontmatter(content)
        assert "step one" in fm["steps"]
        assert "step two" in fm["steps"]

    def test_no_frontmatter(self):
        content = "just body content"
        fm = _parse_frontmatter(content)
        assert fm == {}

    def test_incomplete_frontmatter(self):
        """只有开头的 --- 没结尾"""
        content = """---
name: incomplete"""
        fm = _parse_frontmatter(content)
        assert fm == {}


# ==================== Skill 加载 ====================

class TestLoadSkillFile:

    def test_load_valid_skill(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("""---
name: test
description: test skill
triggers:
  - 测试
  - test
---
This is the body.""", encoding="utf-8")
        skill = load_skill_file(f)
        assert skill is not None
        assert skill.name == "test"
        assert skill.description == "test skill"
        assert "测试" in skill.triggers
        assert "This is the body." in skill.body

    def test_load_uses_stem_when_no_name(self, tmp_path):
        f = tmp_path / "no-name-skill.md"
        f.write_text("""---
description: nameless
---
body""", encoding="utf-8")
        skill = load_skill_file(f)
        assert skill is not None
        assert skill.name == "no-name-skill"

    def test_load_uses_body_as_steps_when_no_steps(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("""---
name: x
description: no steps field
---
Just the body content""", encoding="utf-8")
        skill = load_skill_file(f)
        assert "Just the body content" in skill.steps

    def test_load_nonexistent_file(self, tmp_path):
        skill = load_skill_file(tmp_path / "missing.md")
        assert skill is None


# ==================== Skill 发现 ====================

class TestDiscoverSkills:

    def test_discover_empty(self, tmp_path, monkeypatch):
        # Patch 用户目录为空
        import fr_cli.agent.skills as skills_mod
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", tmp_path / "empty_user")
        skills = discover_skills(cwd=tmp_path)
        assert skills == []

    def test_discover_project_skill(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", tmp_path / "empty_user")

        project_skills = tmp_path / ".fr_cli" / "skills"
        project_skills.mkdir(parents=True)
        (project_skills / "review.md").write_text("""---
name: review
description: 审查
---
body""", encoding="utf-8")

        skills = discover_skills(cwd=tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "review"

    def test_discover_user_skill(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        (user_dir / "user-skill.md").write_text("""---
name: user-skill
description: user skill
---
body""", encoding="utf-8")

        skills = discover_skills(cwd=tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "user-skill"

    def test_project_overrides_user(self, tmp_path, monkeypatch):
        """同名 skill 项目级优先"""
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        project_skills = tmp_path / ".fr_cli" / "skills"
        project_skills.mkdir(parents=True)
        (user_dir / "shared.md").write_text("""---
name: shared
description: user version
---
user version""", encoding="utf-8")
        (project_skills / "shared.md").write_text("""---
name: shared
description: project version
---
project version""", encoding="utf-8")

        skills = discover_skills(cwd=tmp_path)
        assert len(skills) == 1
        assert "project version" in skills[0].body


# ==================== 查找 ====================

class TestFindSkill:

    def test_find_by_name(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        (user_dir / "my-skill.md").write_text("---\nname: my-skill\n---\nbody", encoding="utf-8")

        skill = find_skill_by_name("my-skill", cwd=tmp_path)
        assert skill is not None
        assert skill.name == "my-skill"

    def test_find_by_name_not_found(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", tmp_path / "empty")
        skill = find_skill_by_name("never", cwd=tmp_path)
        assert skill is None

    def test_find_by_trigger_chinese(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        (user_dir / "deploy.md").write_text("""---
name: deploy
triggers:
  - 部署
  - deploy
---
body""", encoding="utf-8")

        skill = find_skill_by_trigger("帮我部署一下应用", cwd=tmp_path)
        assert skill is not None
        assert skill.name == "deploy"

    def test_find_by_trigger_english(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        (user_dir / "deploy.md").write_text("""---
name: deploy
triggers:
  - deploy
---
body""", encoding="utf-8")

        skill = find_skill_by_trigger("please deploy this", cwd=tmp_path)
        assert skill is not None

    def test_find_by_trigger_no_match(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        (user_dir / "x.md").write_text("---\nname: x\ntriggers:\n  - xxx\n---\n", encoding="utf-8")

        skill = find_skill_by_trigger("just random text", cwd=tmp_path)
        assert skill is None


# ==================== 列出 ====================

class TestListSkills:

    def test_list_empty(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", tmp_path / "empty")
        out = list_skills(cwd=tmp_path)
        assert "暂无" in out

    def test_list_with_skills(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "user_skills"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        (user_dir / "a.md").write_text("---\nname: a\ndescription: skill A\n---\n", encoding="utf-8")
        (user_dir / "b.md").write_text("---\nname: b\ndescription: skill B\n---\n", encoding="utf-8")

        out = list_skills(cwd=tmp_path)
        assert "skill A" in out
        assert "skill B" in out
        assert "共 2 个" in out


# ==================== 安装 ====================

class TestInstallSkill:

    def test_install_creates_file(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "new_user_skills"
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        result = install_skill_template(
            name="test-skill",
            description="测试 skill",
            triggers=["test", "测试"],
            steps="1. step 1\n2. step 2",
        )
        assert "已安装" in result

        target = user_dir / "test-skill.md"
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "test-skill" in content
        assert "测试 skill" in content
        assert "step 1" in content

    def test_install_duplicate_fails(self, tmp_path, monkeypatch):
        import fr_cli.agent.skills as skills_mod
        user_dir = tmp_path / "dup_user"
        user_dir.mkdir()
        monkeypatch.setattr(skills_mod, "SKILL_USER_DIR", user_dir)

        install_skill_template(name="dup", description="d", triggers=["x"], steps="1")
        result = install_skill_template(name="dup", description="d", triggers=["x"], steps="1")
        assert "已存在" in result
