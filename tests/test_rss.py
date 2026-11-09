from apex.rss import allowed_link,extract_items

def test_valid_source():
    assert allowed_link('https://arxiv.org/abs/1234.5678')

def test_reject_injected_or_foreign():
    for link in ['javascript:alert(1)','https://evil.org/a','http://arxiv.org/a', 'https://arxiv.org.evil.org/a','https://user@arxiv.org/a']:
        assert not allowed_link(link)

def test_rss_basic():
    raw=b'<rss><channel><item><title>Safe Paper</title><link>https://arxiv.org/abs/1234</link></item><item><title>Bad</title><link>https://evil.org/abc</link></item></channel></rss>'
    assert extract_items(raw)==[('Safe Paper','https://arxiv.org/abs/1234')]
