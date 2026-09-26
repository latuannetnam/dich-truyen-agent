from dich_truyen_agent.crawl_batch import extract_catalog_intro


def test_extract_catalog_intro_strips_scripts_styles_and_links():
    html = """
    <html>
      <head>
        <title>仙府长生 - 飘天文学</title>
        <style>.hide { display: none; }</style>
        <script>var x = 1;</script>
      </head>
      <body>
        <div class="nav">Nav content</div>
        <div class="intro">
          <h1>仙府长生</h1>
          <div>作者：长亭空省</div>
          <p>凡人修仙传同人，讲述散修在仙府中的修仙故事...</p>
        </div>
        <div class="centent">
          <ul>
            <li><a href="1.html">第一章</a></li>
            <li><a href="2.html">第二章</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    intro = extract_catalog_intro(html, chapter_link_selector=".centent ul li a", max_chars=1000)
    assert "仙府长生" in intro
    assert "长亭空省" in intro
    assert "修仙故事" in intro
    assert "第一章" not in intro
    assert "var x = 1" not in intro
    assert len(intro) <= 1000


def test_extract_catalog_intro_handles_empty_html():
    assert extract_catalog_intro("") == ""
    assert extract_catalog_intro(None) == ""
