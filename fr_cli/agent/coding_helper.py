"""
增强代码助手功能
================

参考 OpenCode, Cline, Cursor 等工具的功能增强：
1. 项目级代码理解
2. 多文件编辑
3. 计划-执行模式
4. 权限控制
5. Git 集成
6. 代码审查
7. 学习辅导
"""

import os
import re
import json
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


# ============ 代码理解系统 ============

class CodeUnderstanding:
    """
    代码理解系统
    - 分析项目结构
    - 理解代码关系
    - 识别代码模式
    """

    def __init__(self, project_root: str = "."):
        self.project_root = project_root

    def analyze_structure(self) -> Dict[str, Any]:
        """分析项目结构"""
        structure = {
            "files": [],
            "directories": [],
            "languages": {},
            "frameworks": [],
            "dependencies": {}
        }

        for root, dirs, files in os.walk(self.project_root):
            # 跳过隐藏文件和目录
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                if file.startswith('.'):
                    continue

                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, self.project_root)

                # 检测语言
                ext = os.path.splitext(file)[1]
                lang = self._get_language(ext)
                if lang:
                    if lang not in structure["languages"]:
                        structure["languages"][lang] = []
                    structure["languages"][lang].append(rel_path)

                # 检测框架
                framework = self._detect_framework(file, root)
                if framework and framework not in structure["frameworks"]:
                    structure["frameworks"].append(framework)

                structure["files"].append(rel_path)

            for d in dirs:
                if not d.startswith('.'):
                    structure["directories"].append(os.path.relpath(os.path.join(root, d), self.project_root))

        return structure

    def _get_language(self, ext: str) -> Optional[str]:
        """根据扩展名识别语言"""
        lang_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.go': 'Go',
            '.rs': 'Rust',
            '.cpp': 'C++',
            '.c': 'C',
            '.cs': 'C#',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.json': 'JSON',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.md': 'Markdown',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.bash': 'Bash',
        }
        return lang_map.get(ext)

    def _detect_framework(self, filename: str, filepath: str) -> Optional[str]:
        """检测框架"""
        if filename == 'package.json':
            return 'Node.js'
        elif filename == 'requirements.txt':
            return 'Python'
        elif filename == 'Cargo.toml':
            return 'Rust'
        elif filename == 'go.mod':
            return 'Go'
        elif filename == 'pom.xml':
            return 'Maven'
        elif filename == 'build.gradle':
            return 'Gradle'
        elif filename == 'Dockerfile':
            return 'Docker'
        return None

    def find_related_files(self, target_file: str) -> List[str]:
        """查找相关文件"""
        related = []
        base = os.path.splitext(target_file)[0]

        for root, _, files in os.walk(self.project_root):
            for f in files:
                if f.startswith('.'):
                    continue
                fbase = os.path.splitext(f)[0]
                if fbase == base or target_file in os.path.join(root, f):
                    related.append(os.path.join(root, f))

        return related

    def understand_dependencies(self, file_path: str) -> Dict[str, List[str]]:
        """理解代码依赖关系"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            imports = re.findall(r'(?:import|from)\s+([\w.]+)', content)
            requires = re.findall(r'require\([\'"]([\w./]+[\'"]\)', content)

            return {
                'imports': imports,
                'requires': requires
            }
        except Exception:
            return {'imports': [], 'requires': []}


# ============ 多文件编辑器 ============

@dataclass
class FileEdit:
    """文件编辑操作"""
    path: str
    action: str  # create/edit/delete
    content: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None


class MultiFileEditor:
    """
    多文件编辑器
    支持批量修改多个文件
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.edits: List[FileEdit] = []
        self.results: List[Dict[str, Any]] = []

    def add_edit(self, path: str, action: str, content: str = None,
                 line_start: int = None, line_end: int = None):
        """添加编辑操作"""
        edit = FileEdit(
            path=path,
            action=action,
            content=content,
            line_start=line_start,
            line_end=line_end
        )
        self.edits.append(edit)
        return self

    def execute(self) -> List[Dict[str, Any]]:
        """执行所有编辑"""
        self.results.clear()

        for edit in self.edits:
            result = self._execute_single(edit)
            self.results.append(result)

        return self.results

    def _execute_single(self, edit: FileEdit) -> Dict[str, Any]:
        """执行单个编辑"""
        if self.dry_run:
            return {
                'path': edit.path,
                'action': edit.action,
                'status': 'dry_run',
                'message': f"Would {edit.action} {edit.path}"
            }

        try:
            if edit.action == 'create':
                os.makedirs(os.path.dirname(edit.path), exist_ok=True)
                with open(edit.path, 'w', encoding='utf-8') as f:
                    f.write(edit.content or '')
                return {
                    'path': edit.path,
                    'action': 'create',
                    'status': 'success'
                }

            elif edit.action == 'edit':
                if edit.content:
                    with open(edit.path, 'w', encoding='utf-8') as f:
                        f.write(edit.content)
                return {
                    'path': edit.path,
                    'action': 'edit',
                    'status': 'success'
                }

            elif edit.action == 'delete':
                if os.path.exists(edit.path):
                    os.remove(edit.path)
                return {
                    'path': edit.path,
                    'action': 'delete',
                    'status': 'success'
                }

        except Exception as e:
            return {
                'path': edit.path,
                'action': edit.action,
                'status': 'error',
                'error': str(e)
            }


# ============ 计划-执行系统 ============

@dataclass
class PlanStep:
    """计划步骤"""
    step_id: int
    description: str
    action: str
    files: List[str] = field(default_factory=list)
    approved: bool = False
    executed: bool = False
    result: str = ""


class PlanExecutionSystem:
    """
    计划-执行系统
    先规划，后执行，用户批准后再执行
    """

    def __init__(self):
        self.steps: List[PlanStep] = []
        self.current_step = 0

    def create_plan(self, task: str) -> List[PlanStep]:
        """创建计划"""
        self.steps.clear()
        self.current_step = 0

        # 简单的计划生成逻辑
        if '分析' in task or 'understand' in task.lower():
            self.steps.append(PlanStep(
                step_id=1,
                description="分析代码结构和依赖",
                action="analyze"
            ))
            self.steps.append(PlanStep(
                step_id=2,
                description="生成分析报告",
                action="report"
            ))

        elif '修改' in task or 'edit' in task.lower():
            self.steps.append(PlanStep(
                step_id=1,
                description="读取目标文件",
                action="read"
            ))
            self.steps.append(PlanStep(
                step_id=2,
                description="应用代码修改",
                action="edit"
            ))
            self.steps.append(PlanStep(
                step_id=3,
                description="验证修改",
                action="verify"
            ))

        elif '测试' in task or 'test' in task.lower():
            self.steps.append(PlanStep(
                step_id=1,
                description="生成测试用例",
                action="generate_tests"
            ))
            self.steps.append(PlanStep(
                step_id=2,
                description="运行测试验证",
                action="run_tests"
            ))

        else:
            self.steps.append(PlanStep(
                step_id=1,
                description="理解任务需求",
                action="understand"
            ))
            self.steps.append(PlanStep(
                step_id=2,
                description="执行任务",
                action="execute"
            ))

        return self.steps

    def approve_step(self, step_id: int) -> bool:
        """批准步骤"""
        for step in self.steps:
            if step.step_id == step_id:
                step.approved = True
                return True
        return False

    def execute_step(self, step_id: int, result: str = ""):
        """执行步骤"""
        for step in self.steps:
            if step.step_id == step_id and step.approved:
                step.executed = True
                step.result = result
                return True
        return False

    def get_next_pending_step(self) -> Optional[PlanStep]:
        """获取下一个待执行步骤"""
        for step in self.steps:
            if step.approved and not step.executed:
                return step
        return None


# ============ Git 集成 ============

class GitIntegration:
    """
    Git 集成
    - 查看 diff
    - 提交更改
    - 分支管理
    """

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def get_status(self) -> str:
        """获取 git status"""
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'status', '--short'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            return result.stdout or "Not a git repository"
        except Exception as e:
            return f"Git error: {e}"

    def get_diff(self, file: str = None) -> str:
        """获取 diff"""
        import subprocess
        try:
            cmd = ['git', 'diff']
            if file:
                cmd.append(file)

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            return result.stdout or "No changes"
        except Exception as e:
            return f"Git error: {e}"

    def stage_file(self, file: str) -> bool:
        """暂存文件"""
        import subprocess
        try:
            subprocess.run(
                ['git', 'add', file],
                cwd=self.repo_path,
                check=True
            )
            return True
        except Exception:
            return False

    def commit(self, message: str) -> bool:
        """提交更改"""
        import subprocess
        try:
            subprocess.run(
                ['git', 'commit', '-m', message],
                cwd=self.repo_path,
                check=True
            )
            return True
        except Exception:
            return False

    def get_branches(self) -> List[str]:
        """获取分支列表"""
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'branch', '-a'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            return result.stdout.strip().split('\n')
        except Exception:
            return []


# ============ 代码审查系统 ============

@dataclass
class ReviewFinding:
    """审查发现"""
    severity: str  # high/medium/low
    file: str
    line: int
    message: str
    suggestion: str


class CodeReviewer:
    """
    代码审查系统
    - 发现潜在bug
    - 优化建议
    - 安全漏洞
    """

    def __init__(self):
        self.findings: List[ReviewFinding] = []

    def review_file(self, filepath: str) -> List[ReviewFinding]:
        """审查单个文件"""
        self.findings.clear()

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for i, line in enumerate(lines, 1):
                # 检查常见问题
                if re.search(r'TODO.*(?:fixme|hack|bug', line, re.I):
                    self.findings.append(ReviewFinding(
                        severity='medium',
                        file=filepath,
                        line=i,
                        message='包含 TODO fixme/hack/bug 标记',
                        suggestion='建议立即处理或添加详细说明'
                    ))

                # 检查硬编码密码
                if re.search(r'(?:password|secret|api_key)\s*=\s*["\'][^"\']{3,}["\']', line, re.I):
                    self.findings.append(ReviewFinding(
                        severity='high',
                        file=filepath,
                        line=i,
                        message='检测到可能的硬编码密码或密钥',
                        suggestion='使用环境变量或配置文件'
                    ))

                # 检查未处理的异常
                if 'except:' in line and 'except Exception' not in line:
                    self.findings.append(ReviewFinding(
                        severity='medium',
                        file=filepath,
                        line=i,
                        message='空的异常捕获',
                        suggestion='至少记录异常日志'
                    ))

                # 检查 SQL 注入风险
                if re.search(r'(?:execute|query|cursor)\s*\(.*\%s.*\%s', line, re.I):
                    self.findings.append(ReviewFinding(
                        severity='high',
                        file=filepath,
                        line=i,
                        message='可能的 SQL 注入风险',
                        suggestion='使用参数化查询'
                    ))

        except Exception as e:
            pass

        return self.findings

    def review_project(self, project_root: str) -> List[ReviewFinding]:
        """审查整个项目"""
        all_findings = []

        for root, _, files in os.walk(project_root):
            for file in files:
                if file.startswith('.'):
                    continue

                filepath = os.path.join(root, file)
                findings = self.review_file(filepath)
                all_findings.extend(findings)

        return all_findings

    def format_report(self, findings: List[ReviewFinding]) -> str:
        """格式化审查报告"""
        if not findings:
            return "✅ 未发现问题"

        report = ["\n🔍 代码审查报告\n"]

        high = [f for f in findings if f.severity == 'high']
        medium = [f for f in findings if f.severity == 'medium']
        low = [f for f in findings if f.severity == 'low']

        if high:
            report.append("\n🚨 高风险问题:")
            for f in high:
                report.append(f"  {f.file}:{f.line} - {f.message}")
                report.append(f"  建议: {f.suggestion}\n")

        if medium:
            report.append("\n⚠️ 中风险问题:")
            for f in medium:
                report.append(f"  {f.file}:{f.line} - {f.message}")
                report.append(f"  建议: {f.suggestion}\n")

        return "\n".join(report)


# ============ 学习辅导系统 ============

class LearningTutor:
    """
    学习辅导系统
    - 解释概念
    - 生成示例
    - 回答问题
    """

    @staticmethod
    def explain_concept(concept: str) -> str:
        """解释概念"""
        explanations = {
            'oop': """
面向对象编程 (OOP) 三大特性：
1. 封装 (Encapsulation)
   - 将数据和操作数据的方法打包到类中
   - 对外提供接口，隐藏内部实现

2. 继承 (Inheritance)
   - 子类继承父类的属性和方法
   - 支持代码复用

3. 多态 (Polymorphism)
   - 同一接口不同实现
   - 父类引用指向子类对象
            """,
            'closure': """
闭包 (Closure) 解释：
闭包是引用了外部变量的函数。
特性：
- 函数可以记住创建时的环境
- 内部函数可以访问外部函数的变量
- 常用于回调、装饰器、延迟执行等场景
            """,
            'async': """
异步编程 (Async/Await) 核心概念：
1. 协程 (Coroutine)
   - 比线程更轻量的并发单位
   - 由程序控制切换，而非操作系统

2. 事件循环 (Event Loop)
   - 处理 I/O 密集型任务
   - 单线程执行异步代码

3. await/async
   - async 定义协程函数
   - await 等待协程完成
            """
        }

        concept_lower = concept.lower()
        for key, explanation in explanations.items():
            if key in concept_lower:
                return explanation

        return f"抱歉，我还没有关于 '{concept}' 的详细解释。\n您可以尝试询问：oop, closure, async 等概念。"

    @staticmethod
    def generate_example(topic: str, language: str = "python") -> str:
        """生成示例代码"""
        examples = {
            'decorator': """Python 装饰器示例：
```python
def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("执行前")
        result = func(*args, **kwargs)
        print("执行后")
        return result
    return wrapper

@my_decorator
def say_hello():
    print("Hello!")

say_hello()
# 输出：
# 执行前
# Hello!
# 执行后
```""",
            'class': """Python 类定义示例：
```python
class Animal:
    def __init__(self, name):
        self.name = name

    def speak(self):
        raise NotImplementedError

class Dog(Animal):
    def speak(self):
        return f"{self.name} says Woof!"

class Cat(Animal):
    def speak(self):
        return f"{self.name} says Meow!"

dog = Dog("Buddy")
print(dog.speak())  # 输出: Buddy says Woof!
```"""
        }

        topic_lower = topic.lower()
        for key, example in examples.items():
            if key in topic_lower:
                return example

        return f"抱歉，我还没有关于 '{topic}' 的示例代码。\n可以尝试询问：decorator, class 等。"

    @staticmethod
    def suggest_learning_path(current_level: str) -> str:
        """建议学习路径"""
        paths = {
            'beginner': """
📚 初级开发者学习路径：

1. Python/JavaScript 基础
   - 语法、数据类型、控制流
   - 练习：100+ 算法题

2. 数据结构
   - 数组、链表、树、图
   - 练习：实现基本数据结构

3. 算法
   - 排序、查找、动态规划
   - 练习：LeetCode 中等难度题

4. Web 基础
   - HTTP、REST API
   - 前端 HTML/CSS/JS
   - 后端 Flask/Django/Express

5. 数据库
   - SQL 基础
   - Redis/MongoDB
   - 练习：CRUD 应用
            """,
            'intermediate': """
📚 中级开发者学习路径：

1. 设计模式
   - 单例、工厂、策略、观察者
   - 练习：重构现有代码

2. 并发编程
   - 线程、进程、协程
   - 练习：实现并发服务器

3. 分布式系统
   - 消息队列、缓存、负载均衡
   - 学习 Kafka、Redis、Docker

4. 测试
   - 单元测试、集成测试
   - 练习：TDD 开发

5. 云服务
   - AWS/GCP/Azure 基础
   - K8s、Terraform
            """
        }

        return paths.get(current_level.lower(), paths['beginner'])


# ============ 导出 ============

def run(context: Dict, **kwargs) -> str:
    """
    增强助手入口

    使用示例：
    【调用：code_understand({"action": "analyze", "path": "."})】
    【调用：code_review({"action": "review_file", "path": "main.py"})】
    【调用：learning({"topic": "closure", "action": "explain"})】
    """
    action = kwargs.get("action", "")

    if action == "analyze":
        understanding = CodeUnderstanding(kwargs.get("path", "."))
        return json.dumps(understanding.analyze_structure(), indent=2, ensure_ascii=False)

    elif action == "review":
        reviewer = CodeReviewer()
        if kwargs.get("file"):
            findings = reviewer.review_file(kwargs["file"])
        else:
            findings = reviewer.review_project(kwargs.get("path", "."))
        return reviewer.format_report(findings)

    elif action == "explain":
        tutor = LearningTutor()
        return tutor.explain_concept(kwargs.get("concept", ""))

    elif action == "example":
        tutor = LearningTutor()
        return tutor.generate_example(
            kwargs.get("topic", ""),
            kwargs.get("language", "python")
        )

    elif action == "path":
        tutor = LearningTutor()
        return tutor.suggest_learning_path(kwargs.get("level", "beginner"))

    elif action == "git_status":
        git = GitIntegration(kwargs.get("repo", "."))
        return git.get_status()

    elif action == "git_diff":
        git = GitIntegration(kwargs.get("repo", "."))
        return git.get_diff(kwargs.get("file"))

    else:
        return """可用操作：
- analyze: 分析项目结构
- review: 代码审查
- explain: 解释概念
- example: 生成示例代码
- path: 学习路径建议
- git_status: Git 状态
- git_diff: Git 差异"""


if __name__ == "__main__":
    print("""
🔧 代码助手增强功能

功能：
  📊 项目分析：理解代码结构
  📝 多文件编辑：批量修改代码
  📋 计划执行：先规划后操作
  🔍 代码审查：发现潜在问题
  📚 学习辅导：解释概念和示例
  🐙 Git 集成：版本控制

使用示例：
  run({"action": "analyze", "path": "."})
  run({"action": "review", "file": "main.py"})
  run({"action": "explain", "concept": "closure"})
    """)
