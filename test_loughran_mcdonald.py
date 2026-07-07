from fvn_dfm.text.html_cleaner import clean_sec_html_to_text, count_words, normalize_whitespace, text_length_diagnostics


def test_normalize_whitespace():
    assert normalize_whitespace(" A\n\tB&nbsp; C ") == "A B C"


def test_clean_sec_html_to_text_removes_scripts_styles_tables():
    raw = """
    <html><head><style>.x{}</style><script>alert(1)</script></head>
    <body><p>Management discussion text.</p><table><tr><td>123</td></tr></table></body></html>
    """
    clean = clean_sec_html_to_text(raw, remove_tables=True)
    assert "Management discussion text." in clean
    assert "alert" not in clean
    assert "123" not in clean


def test_count_words_and_diagnostics():
    raw = "<html><body>Hello world.</body></html>"
    clean = clean_sec_html_to_text(raw)
    assert count_words(clean) == 2
    d = text_length_diagnostics(raw, clean)
    assert d["raw_char_count"] > d["clean_char_count"]
    assert d["clean_word_count"] == 2
