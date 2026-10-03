"""E2E: markdown -> HTML редактора (jsdom) -> markdown для формы -> опубликованная страница.

Проверяет, что переносы строк и блочное форматирование не теряются при
редактировании статьи в едином поле.
"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["ARTICLES_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "articles_test.db")
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
from web.app import app
from web.auth import create_session_cookie

MD_INPUT = (
    "Дайджест на выходные уже в сети\n\n"
    "Т.е. всегда должен быть текст?\n\n"
    "## САМОЕ АКТУАЛЬное тут\n\n"
    "### А вот чуть поменьше текс\n\n"
    "1. Ебать реально\n2. Ну все\n3. Вика должна быть довольна\n\n"
    "Хмм, интересно... Но конечно это еще дорабатывать и дебажить..."
)

client = TestClient(app)
client.cookies.set("gigs_session", create_session_cookie("tehnokrat"))
html_page = client.get("/admin/articles/new").text
m = re.search(r"<script>\n(\(function \(\).*?)\n</script>", html_page, re.DOTALL)
assert m, "editor script not found in page"
open("/tmp/editor.js", "w").write(m.group(1))

NODE = r"""
const fs = require('fs');
const { JSDOM } = require('jsdom');
const editorSrc = fs.readFileSync('/tmp/editor.js', 'utf8');
const md = process.env.MD_INPUT;
const esc = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
const dom = new JSDOM(`<!doctype html><body>
<form class="article-form">
<textarea id="body" name="body" hidden>` + esc(md) + `</textarea>
<div id="bodyEditor" contenteditable="true"></div>
<input id="cover_image_url" value="">
<div id="coverPreview" class="hidden"><img id="coverPreviewImg"></div>
<div id="editorToolbar"></div>
<input id="coverFile" type="file"><input id="bodyImageFile" type="file">
<button id="insertImageBtn"></button>
</form></body>`, { runScripts: 'outside-only', pretendToBeVisual: true });
// window в jsdom outside-only существует; скрипт использует document/window — eval в контексте
dom.window.eval(editorSrc);
const ta = dom.window.document.getElementById('body');
const ed = dom.window.document.getElementById('bodyEditor');
const step1 = ed.innerHTML;   // renderEditor() отработал при загрузке
// имитируем submit: событие submit на форме -> syncFromEditor()
const form = dom.window.document.querySelector('.article-form');
form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));
console.log(JSON.stringify({ step1, back: ta.value }));
"""
env = dict(os.environ, MD_INPUT=MD_INPUT)
res = subprocess.run(["node", "-e", NODE], capture_output=True, text=True, env=env, cwd=ROOT)
if res.returncode != 0:
    print(res.stderr[-3000:]); sys.exit(1)
data = json.loads(res.stdout)
print("--- editor HTML (что видит редактор) ---")
print(data["step1"])
print("--- markdown после submit (уходит на сервер) ---")
print(repr(data["back"]))
assert data["back"].strip() == MD_INPUT.strip(), \
    f"roundtrip mismatch:\n{data['back']!r}\nvs\n{MD_INPUT!r}"

# сохранение статьи реальным POST + чтение опубликованной страницы
r = client.post("/admin/articles/new",
                data={"title": "Тест переносов", "kind": "article", "lead": "",
                      "cover_image_url": "", "body": data["back"], "publish": "1"},
                follow_redirects=False)
assert r.status_code in (200, 302, 303), r.status_code
from web.articles_db import Article, get_article_session
with get_article_session() as s:
    a = s.query(Article).order_by(Article.id.desc()).first()
    slug = a.slug
    assert a.body == data["back"], "server changed body line breaks!"
page = client.get(f"/articles/{slug}").text
i = page.find('class="article-body"')
frag = page[i:i+3000]
print("--- published article fragment ---")
print(frag[:1200])
for token in ("<h2", "САМОЕ АКТУАЛЬное тут", "<h3", "А вот чуть поменьше текс",
              "<ol", "Ебать реально", "Ну все", "Вика должна быть довольна",
              "Хмм, интересно"):
    assert token in frag, f"MISSING in published page: {token}"
assert "текс1." not in frag and "тут##" not in frag and "довольнаХмм" not in frag
print("ALL E2E CHECKS PASSED")
