from app.services.whatsapp_format import markdown_to_whatsapp, parse_reply_directives


def test_markdown_bold_and_italic_become_whatsapp_syntax():
    assert markdown_to_whatsapp("**hola** y __esto__ y ~~eso~~") == "*hola* y _esto_ y ~eso~"


def test_headings_become_bold_lines():
    assert markdown_to_whatsapp("## Postres\n- Tiramisú") == "*Postres*\n- Tiramisú"


def test_star_bullets_become_dashes():
    assert markdown_to_whatsapp("* uno\n* dos") == "- uno\n- dos"


def test_links_keep_text_and_url():
    assert markdown_to_whatsapp("Mira [el menú](https://x.co/m)") == "Mira el menú (https://x.co/m)"


def test_tables_degrade_to_plain_lines():
    text = "| Pizza | Precio |\n|---|---|\n| Caprese | $22 |"
    assert markdown_to_whatsapp(text) == "Pizza · Precio\nCaprese · $22"


def test_plain_text_untouched():
    assert markdown_to_whatsapp("hola, ¿cómo estás?") == "hola, ¿cómo estás?"


def test_parse_react_directive():
    assert parse_reply_directives("[react: 👍]") == ("", "👍", None)


def test_parse_react_with_text_and_quote():
    clean, emoji, quote = parse_reply_directives("[react: ❤️]\n[quote: 2]\nClaro que sí")
    assert (clean, emoji, quote) == ("Claro que sí", "❤️", 2)


def test_malformed_directives_are_dropped():
    assert parse_reply_directives("[react: thumbsup] hola") == ("hola", None, None)
    assert parse_reply_directives("[quote: dos] hola") == ("hola", None, None)


def test_text_without_directives_untouched():
    assert parse_reply_directives("Con gusto [react: 👍] no aplica") == ("Con gusto [react: 👍] no aplica", None, None)
