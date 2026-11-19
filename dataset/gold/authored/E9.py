# -*- coding: utf-8 -*-
"""自写金测试：E9 — 非正 --line-length 应被拒绝（上游 fix 0b2b5e59 未带测试）。

fix 把 click option 的 type=int 改为 IntRange(min=1)。
fix^：int 接受 0/-5 → 正常格式化 exit 0 → 断言失败（fail-before ✓）。
fix：IntRange 拒绝 → exit 2 ✓。
"""

from click.testing import CliRunner

from black import main


def test_non_positive_line_length_rejected(tmp_path):
    f = tmp_path / "t.py"
    f.write_text("x = 1\n", encoding="utf-8")
    runner = CliRunner()
    for bad in ("0", "-5"):
        result = runner.invoke(main, ["--line-length", bad, str(f)])
        assert result.exit_code != 0, f"--line-length {bad} should be rejected"
