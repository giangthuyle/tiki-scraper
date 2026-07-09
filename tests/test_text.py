from tiki_scraper.text import html_to_text


def test_strips_tags():
    assert html_to_text("<p><strong>Hello</strong> world</p>") == "Hello world"


def test_collapses_whitespace():
    assert html_to_text("<p>Hello    \n\n  world</p>") == "Hello world"


def test_unescapes_entities():
    assert html_to_text("<p>Toa &amp; xe &ndash; 100%</p>") == "Toa & xe – 100%"


def test_separates_block_elements_with_newlines():
    assert html_to_text("<p>A</p><p>B</p><ul><li>C</li><li>D</li></ul>") == "A\nB\nC\nD"


def test_empty_input():
    assert html_to_text("") == ""
