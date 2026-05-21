#!/usr/bin/env python3
"""
Nexus Self-Evaluation Module — Auto-evaluación de calidad para Nexus Videojuego / ONEIROS.

Proporciona evaluación automatizada de la calidad del proyecto en 7 dimensiones:
1. Code Quality — Estructura, tipos, docstrings
2. Test Coverage — Existencia y cobertura de tests
3. Documentation — README, SOUL.md, docstrings
4. Error Handling — Try/catch, validación, mensajes claros
5. No Stubs — Sin datos falsos, mocks en producción
6. Rotatron Integration — Integración con continuación automática
7. Status Reporting — Formato estandarizado de informes

Uso:
    from nexus.self_evaluate import NexusSelfEvaluator
    evaluator = NexusSelfEvaluator("/root/nexus")
    report = evaluator.evaluate()
    print(report.summary())
"""

from __future__ import annotations

import ast
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalResult:
    """Resultado de una dimensión de evaluación."""
    dimension: str
    score: float  # 0-10
    max_score: float = 10.0
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 7.0

    def __repr__(self) -> str:
        status = "✅" if self.passed else "❌"
        return f"{status} {self.dimension}: {self.score:.1f}/{self.max_score}"


@dataclass
class EvalReport:
    """Reporte completo de auto-evaluación."""
    project_path: str
    results: list[EvalResult] = field(default_factory=list)
    timestamp: str = ""

    @property
    def total_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "🧪 NEXUS SELF-EVALUATION REPORT",
            "=" * 60,
            f"Proyecto: {self.project_path}",
            f"Score total: {self.total_score:.1f}/10",
            f"Estado: {'✅ APROBADO' if self.all_passed else '❌ NECESITA MEJORAS'}",
            "-" * 60,
        ]
        for r in self.results:
            status = "✅" if r.passed else "❌"
            lines.append(f"  {status} {r.dimension}: {r.score:.1f}/10")
            for issue in r.issues:
                lines.append(f"      ⚠️  {issue}")
            for rec in r.recommendations:
                lines.append(f"      💡 {rec}")
        lines.append("-" * 60)
        lines.append(f"Score final: {self.total_score:.1f}/10")
        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "total_score": round(self.total_score, 1),
            "all_passed": self.all_passed,
            "results": [
                {
                    "dimension": r.dimension,
                    "score": r.score,
                    "max_score": r.max_score,
                    "passed": r.passed,
                    "issues": r.issues,
                    "recommendations": r.recommendations,
                }
                for r in self.results
            ],
        }


class NexusSelfEvaluator:
    """Evaluador automático de calidad para el proyecto Nexus."""

    def __init__(self, project_path: str = "/root/nexus") -> None:
        self.project_path = Path(project_path)
        self._py_files: list[Path] | None = None

    @property
    def py_files(self) -> list[Path]:
        if self._py_files is None:
            self._py_files = sorted(
                f for f in self.project_path.rglob("*.py")
                if "__pycache__" not in str(f) and "site-packages" not in str(f)
            )
        return self._py_files

    def evaluate(self) -> EvalReport:
        """Ejecuta todas las dimensiones de evaluación y retorna el reporte."""
        from datetime import datetime, timezone
        report = EvalReport(
            project_path=str(self.project_path),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        report.results.append(self._eval_code_quality())
        report.results.append(self._eval_test_coverage())
        report.results.append(self._eval_documentation())
        report.results.append(self._eval_error_handling())
        report.results.append(self._eval_no_placeholders())
        report.results.append(self._eval_rotatron_integration())
        report.results.append(self._eval_status_reporting())

        return report

    def _eval_code_quality(self) -> EvalResult:
        """Evalúa calidad del código: tipos, docstrings, estructura."""
        result = EvalResult(dimension="Code Quality", score=10.0)
        total_funcs = 0
        documented_funcs = 0
        typed_funcs = 0

        for py_file in self.py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError) as e:
                result.issues.append(f"Syntax error in {py_file.name}: {e}")
                result.score -= 2.0
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_funcs += 1
                    if ast.get_docstring(node):
                        documented_funcs += 1
                    if node.returns is not None:
                        typed_funcs += 1

        if total_funcs > 0:
            doc_ratio = documented_funcs / total_funcs
            type_ratio = typed_funcs / total_funcs

            if doc_ratio < 0.5:
                result.score -= 2.0
                result.issues.append(
                    f"Only {doc_ratio:.0%} of functions have docstrings (target: ≥50%)"
                )
                result.recommendations.append("Add docstrings to all public functions")
            elif doc_ratio < 0.8:
                result.score -= 0.5
                result.recommendations.append(
                    f"Improve docstring coverage from {doc_ratio:.0%} to ≥80%"
                )

            if type_ratio < 0.5:
                result.score -= 1.5
                result.issues.append(
                    f"Only {type_ratio:.0%} of functions have return type annotations"
                )
                result.recommendations.append("Add return type annotations to all functions")
        else:
            result.issues.append("No functions found in project")
            result.score -= 3.0

        result.score = max(0.0, result.score)
        return result

    def _eval_test_coverage(self) -> EvalResult:
        """Evalúa existencia y calidad de tests."""
        result = EvalResult(dimension="Test Coverage", score=10.0)
        test_dir = self.project_path / "tests"

        if not test_dir.exists():
            result.score = 2.0
            result.issues.append("No tests/ directory found")
            result.recommendations.append("Create tests/ with unit/ and integration/ subdirs")
            return result

        test_files = list(test_dir.rglob("test_*.py")) + list(test_dir.rglob("*_test.py"))
        if not test_files:
            result.score = 3.0
            result.issues.append("No test files found in tests/")
            result.recommendations.append("Add test files with pytest conventions")
            return result

        # Count test functions
        total_tests = 0
        for tf in test_files:
            try:
                source = tf.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(tf))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("test_"):
                            total_tests += 1
            except (SyntaxError, UnicodeDecodeError):
                result.issues.append(f"Cannot parse {tf.name}")

        if total_tests == 0:
            result.score = 4.0
            result.issues.append("No test functions found")
        elif total_tests < 10:
            result.score -= 2.0
            result.recommendations.append(
                f"Only {total_tests} tests found — aim for ≥20 for good coverage"
            )
        elif total_tests < 20:
            result.score -= 0.5

        # Check for conftest.py
        if not (test_dir / "conftest.py").exists():
            result.score -= 0.5
            result.recommendations.append("Add tests/conftest.py for shared fixtures")

        # Check for unit/ and integration/ subdirs
        has_unit = (test_dir / "unit").exists()
        has_integration = (test_dir / "integration").exists()
        if not has_unit:
            result.score -= 0.5
            result.recommendations.append("Create tests/unit/ for unit tests")
        if not has_integration:
            result.score -= 0.5
            result.recommendations.append("Create tests/integration/ for integration tests")

        result.score = max(0.0, result.score)
        return result

    def _eval_documentation(self) -> EvalResult:
        """Evalúa documentación del proyecto."""
        result = EvalResult(dimension="Documentation", score=10.0)

        readme = self.project_path / "README.md"
        if not readme.exists():
            result.score -= 3.0
            result.issues.append("No README.md found")
            result.recommendations.append("Create README.md with project overview")
        else:
            content = readme.read_text(encoding="utf-8")
            if len(content) < 200:
                result.score -= 1.0
                result.recommendations.append("Expand README.md with more detail")

        soul = self.project_path / "SOUL.md"
        if not soul.exists():
            result.score -= 2.0
            result.issues.append("No SOUL.md found")
            result.recommendations.append("Create SOUL.md with agent identity and rules")

        # Check for duplicate sections in SOUL.md
        if soul.exists():
            content = soul.read_text(encoding="utf-8")
            sections = {}
            for line in content.split("\n"):
                if line.startswith("## "):
                    title = line.strip()
                    sections[title] = sections.get(title, 0) + 1
            duplicates = {k: v for k, v in sections.items() if v > 1}
            if duplicates:
                result.score -= 1.5
                for title, count in duplicates.items():
                    result.issues.append(f"Duplicate section in SOUL.md: '{title}' appears {count}x")
                result.recommendations.append("Remove duplicate sections from SOUL.md")

        result.score = max(0.0, result.score)
        return result

    def _eval_error_handling(self) -> EvalResult:
        """Evalúa manejo de errores en el código."""
        result = EvalResult(dimension="Error Handling", score=10.0)
        total_functions = 0
        functions_with_try = 0
        bare_excepts = 0

        for py_file in self.py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_functions += 1
                    has_try = False
                    for child in ast.walk(node):
                        if isinstance(child, ast.Try):
                            has_try = True
                            for handler in child.handlers:
                                if handler.type is None:
                                    bare_excepts += 1
                    if has_try:
                        functions_with_try += 1

        if total_functions > 0:
            # Check for bare excepts
            if bare_excepts > 0:
                result.score -= 2.0
                result.issues.append(f"Found {bare_excepts} bare 'except:' clauses")
                result.recommendations.append("Replace bare 'except:' with specific exception types")

            # Not every function needs try/except, but public API functions should
            public_funcs = total_functions  # simplified
            if public_funcs > 0:
                try_ratio = functions_with_try / public_funcs
                if try_ratio < 0.1 and public_funcs > 10:
                    result.score -= 1.0
                    result.recommendations.append(
                        "Add error handling to more public-facing functions"
                    )

        result.score = max(0.0, result.score)
        return result

    def _eval_no_placeholders(self) -> EvalResult:
        """Evalúa que no haya datos falsos, mocks en producción, o TODOs."""
        result = EvalResult(dimension="No Placeholders", score=10.0)
        # Patterns that indicate stubs/unfinished code in production
        stub_patterns = [
            "TODO", "FIXME", "XXX", "HACK",
            "mock_data", "fake_data", "dummy_data",
        ]

        for py_file in self.py_files:
            # Skip test files and self for placeholder checks
            if "test" in py_file.name or py_file.name == "self_evaluate.py":
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                lines = source.split("\n")
            except (SyntaxError, UnicodeDecodeError):
                continue

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip comments and docstrings
                if stripped.startswith("#") or stripped.startswith('"'):
                    continue
                for pattern in stub_patterns:
                    if pattern in stripped:
                        result.issues.append(
                            f"{py_file.name}:{i} — contains '{pattern}'"
                        )
                        result.score -= 1.0

        result.score = max(0.0, result.score)
        if not result.issues:
            result.score = 10.0
        return result

    def _eval_rotatron_integration(self) -> EvalResult:
        """Evalúa integración con ROTATRON para continuación automática."""
        result = EvalResult(dimension="Rotatron Integration", score=10.0)

        rotatron_file = self.project_path / "rotatron_integration.py"
        if not rotatron_file.exists():
            result.score = 3.0
            result.issues.append("No rotatron_integration.py found")
            result.recommendations.append("Create rotatron_integration.py for ROTATRON notifications")
            return result

        content = rotatron_file.read_text(encoding="utf-8")

        # Check for key functions
        if "notify_nexus_game_complete" not in content:
            result.score -= 2.0
            result.issues.append("Missing notify_nexus_game_complete() function")
            result.recommendations.append("Add notify_nexus_game_complete() for task completion")

        if "get_next_nexus_game_prompt" not in content:
            result.score -= 2.0
            result.issues.append("Missing get_next_nexus_game_prompt() function")
            result.recommendations.append("Add get_next_nexus_game_prompt() for continuation")

        # Check SOUL.md references ROTATRON
        soul = self.project_path / "SOUL.md"
        if soul.exists():
            soul_content = soul.read_text(encoding="utf-8")
            if "ROTATRON" not in soul_content:
                result.score -= 1.0
                result.issues.append("SOUL.md does not mention ROTATRON integration")
                result.recommendations.append("Add ROTATRON section to SOUL.md")

        result.score = max(0.0, result.score)
        return result

    def _eval_status_reporting(self) -> EvalResult:
        """Evalúa formato estandarizado de informes de estado."""
        result = EvalResult(dimension="Status Reporting", score=10.0)

        soul = self.project_path / "SOUL.md"
        if not soul.exists():
            result.score = 5.0
            result.issues.append("No SOUL.md to define status report format")
            return result

        content = soul.read_text(encoding="utf-8")

        required_elements = [
            "INFORME DE ESTADO",
            "Estado:",
            "Hecho:",
            "Falta:",
            "Bloqueos:",
            "Calidad:",
            "Siguiente:",
        ]

        missing = [e for e in required_elements if e not in content]
        if missing:
            result.score -= len(missing) * 0.5
            for m in missing:
                result.issues.append(f"Status report missing element: '{m}'")
            result.recommendations.append(
                "Add all required status report elements to SOUL.md"
            )

        result.score = max(0.0, result.score)
        return result


def nexus_self_evaluate(project_path: str = "/root/nexus") -> EvalReport:
    """Función de conveniencia para auto-evaluación rápida.

    Uso:
        from nexus.self_evaluate import nexus_self_evaluate
        report = nexus_self_evaluate()
        print(report.summary())
        if not report.all_passed:
            FIX_BEFORE_DELIVERING()
    """
    evaluator = NexusSelfEvaluator(project_path)
    return evaluator.evaluate()


if __name__ == "__main__":
    report = nexus_self_evaluate()
    print(report.summary())
    if not report.all_passed:
        print("\n⚠️  ACCIÓN REQUERIDA: Corregir issues antes de continuar")
    else:
        print("\n✅ Proyecto en excelente estado — Listo para ROTATRON")
