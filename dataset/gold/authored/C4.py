# -*- coding: utf-8 -*-
"""自写金测试：C4 — EXTENSION 应被识别为 PLPGSQL 关键词（issue #785）。

上游 fix e48000a 只改了 sqlparse/keywords.py 一行（KEYWORDS_PLPGSQL 加 EXTENSION），
未带测试。本测试在 fix^ 应失败（EXTENSION 是 Name），在 fix 应通过（Keyword）。
默认 Lexer 会 add_keywords(KEYWORDS_PLPGSQL)（lexer.py L65），故默认 parse 即可触发。
"""

import sqlparse
from sqlparse import tokens as T


def test_extension_is_keyword():
    stmt = sqlparse.parse("CREATE EXTENSION pgcrypto;")[0]
    tok = next(t for t in stmt.flatten() if t.value == "EXTENSION")
    assert tok.ttype == T.Keyword, f"EXTENSION got {tok.ttype}, expected Keyword"
