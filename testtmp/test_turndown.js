// Интеграционный тест: htmlToMd на базе Turndown сохраняет структуру блоков
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const dom = new JSDOM(`<!doctype html><html><body>
<textarea id="body"></textarea>
<div id="bodyEditor" contenteditable></div>
<input id="title"><button id="importUrlBtn"></button><button id="insertImageBtn"></button>
<input id="bodyImageFile" type="file" hidden><input id="coverFile" type="file" hidden>
<input id="cover_image_url"><div id="coverPreview"></div><img id="coverPreviewImg">
<div id="editorToolbar"></div><form class="article-form"></form>
</body></html>`, { url: "http://localhost/", runScripts: "outside-only" });

global.window = dom.window;
global.document = dom.window.document;
global.Node = dom.window.Node;
global.NodeFilter = dom.window.NodeFilter;
global.fetch = () => Promise.reject(new Error("no network"));
global.alert = (m) => console.log("ALERT:", m);

// загрузить Turndown в контекст теста
const turndownSrc = fs.readFileSync(path.join(__dirname, "..", "web_static", "js", "turndown.js"), "utf8");
dom.window.eval(turndownSrc);
global.TurndownService = dom.window.TurndownService;

// извлечь inline-скрипт шаблона (Jinja {{...}} -> null) и выполнить его
let srcHtml = fs.readFileSync(path.join(__dirname, "..", "web/templates/admin/article_form.html"), "utf8");
let blocks = [...srcHtml.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
let js = blocks.sort((a,b)=>b.length-a.length)[0].replace(/\{\{[^}]*\}\}/g, "null");
dom.window.eval(js);

const editor = document.getElementById("bodyEditor");
const bodyEl = document.getElementById("body");

// канонический markdown (как после импорта по URL / ручного ввода)
const md = [
  "## Дайджест на выходные уже в сети",
  "",
  "Т.е. всегда должен быть текст?",
  "",
  "## САМОЕ АКТУАЛЬное тут",
  "",
  "### А вот чуть поменьше текс",
  "",
  "1. Ебать реально",
  "2. Ну все",
  "3. Вика должна быть довольна",
  "",
  "Хмм, интересно... Но конечно это еще дорабатывать и дебажить...",
].join("\n");

window.refreshEditor();               // объявлена в скрипте
bodyEl.value = md;
// перерисовать редактор из textarea через публичную функцию
document.getElementById("body").dispatchEvent(new dom.window.Event("x")); // noop
// renderEditor не экспортирован напрямую — используем refreshEditor после установки значения
// (refreshEditor читает bodyEl.value и вызывает mdToPreviewHtml)
window.refreshEditor();

console.log("--- HTML редактора ---");
console.log(editor.innerHTML.slice(0, 400));

// синхронизация обратно: blur вызывает syncFromEditor -> htmlToMd (Turndown)
editor.dispatchEvent(new dom.window.Event("blur"));
const out = bodyEl.value;
console.log("--- Markdown после сохранения ---");
console.log(JSON.stringify(out));

const checks = [
  ["заголовок ## Дайджест отдельной строкой", /\n?## Дайджест на выходные уже в сети\n/.test("\n"+out) && !/сетиТ\.е/.test(out)],
  ["текст не склеен с заголовком", out.includes("Т.е. всегда должен быть текст?")],
  ["## САМОЕ отдельным блоком", /\n\n## САМОЕ АКТУАЛЬное тут\n/.test(out)],
  ["### подзаголовок сохранён", out.includes("### А вот чуть поменьше текс")],
  ["нумерованный список сохранён построчно", /1\. Ебать реально\n2\. Ну все\n3\. Вика должна быть довольна/.test(out)],
  ["последний абзац отдельным блоком", /\n\nХмм, интересно\.\.\./.test(out)],
];
let ok = true;
for (const [name, pass] of checks) { console.log((pass ? "PASS" : "FAIL") + "  " + name); if (!pass) ok = false; }
process.exit(ok ? 0 : 1);
