// Интеграционный тест единого поля редактирования статьи в jsdom.
const fs = require("fs");
const { JSDOM } = require("/tmp/node_modules/jsdom");

const html = fs.readFileSync("/tmp/form_page.html", "utf-8");
const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true });
const win = dom.window;
const doc = win.document;

setTimeout(() => {
  const editor = doc.getElementById("bodyEditor");
  const bodyEl = doc.getElementById("body");
  if (!editor) { console.log("FAIL: no editor"); process.exit(1); }

  const sel = () => win.getSelection();
  let fails = 0;
  function check(name, cond, extra) {
    console.log((cond ? "PASS" : "FAIL") + ": " + name + (cond ? "" : "  -> " + (extra || "")));
    if (!cond) fails++;
  }

  // наполним редактор и синхронизируем через blur
  editor.innerHTML = "<p>Первый абзац.</p><p>Второй абзац.</p><p>Третий абзац.</p>";
  editor.dispatchEvent(new win.Event("blur"));
  check("blur -> markdown в textarea",
    bodyEl.value === "Первый абзац.\n\nВторой абзац.\n\nТретий абзац.",
    JSON.stringify(bodyEl.value));

  // --- курсор во втором абзаце, нажатие H2 ---
  const p2 = editor.children[1];
  const t2 = p2.firstChild;
  const r = doc.createRange();
  r.setStart(t2, 3); r.collapse(true);
  sel().removeAllRanges(); sel().addRange(r);
  doc.querySelector('[data-fmt="h2"]').click();

  check("H2 применился ко второму абзацу", p2.parentNode === editor && p2.tagName === "H2",
    editor.innerHTML);
  check("первый абзац не тронут", editor.children[0].tagName === "P");
  check("третий абзац не тронут", Array.from(editor.children).some(el => el.tagName === "P" && el.textContent.includes("Третий")));
  check("markdown: ## только у второго",
    bodyEl.value === "Первый абзац.\n\n## Второй абзац.\n\nТретий абзац.",
    JSON.stringify(bodyEl.value));
  const s0 = sel().getRangeAt(0);
  const h2el = Array.from(editor.children).find(el => el.tagName === "H2");
  check("курсор остался внутри h2", !!h2el && editor.contains(s0.startContainer) &&
    s0.startContainer.parentElement.closest("h2") === h2el, "caret lost");

  // повторное нажатие H2 -> обратно в P
  doc.querySelector('[data-fmt="h2"]').click();
  check("H2 toggle -> снова P", !editor.querySelector("h2"), editor.innerHTML);
  check("markdown без ## после отмены", !bodyEl.value.includes("##"), JSON.stringify(bodyEl.value));

  // --- список: выделен второй абзац, клик UL ---
  const pB = Array.from(editor.children).find(el => el.textContent.includes("Второй"));
  const range2 = doc.createRange();
  range2.selectNodeContents(pB);
  sel().removeAllRanges(); sel().addRange(range2);
  doc.querySelector('[data-fmt="ul"]').click();
  const ul = editor.querySelector("ul");
  check("создан <ul> с одним пунктом", !!ul && ul.children.length === 1 &&
    ul.children[0].textContent.includes("Второй"), editor.innerHTML);
  check("соседние абзацы вне списка",
    editor.querySelectorAll("p").length >= 2);
  check("markdown: '- ' только у второго",
    bodyEl.value === "Первый абзац.\n\n- Второй абзац.\n\nТретий абзац.",
    JSON.stringify(bodyEl.value));

  // ещё один пункт изнутри списка
  const liR = doc.createRange();
  liR.setStart(ul.children[0].firstChild, 3); liR.collapse(true);
  sel().removeAllRanges(); sel().addRange(liR);
  doc.querySelector('[data-fmt="ul"]').click();
  const ul2 = editor.querySelector("ul");
  check("второй клик в списке -> новый пункт", ul2.children.length === 2,
    ul2.outerHTML);

  // снять список (выделены оба пункта)
  const rr = doc.createRange();
  rr.setStartBefore(ul2.children[0]); rr.setEndAfter(ul2.children[1]);
  sel().removeAllRanges(); sel().addRange(rr);
  doc.querySelector('[data-fmt="ul"]').click();
  check("снятие списка -> абзацы", !editor.querySelector("ul"), editor.innerHTML);

  // --- цитата ---
  const pA = Array.from(editor.children).find(el => el.textContent.includes("Первый"));
  const rq = doc.createRange();
  rq.selectNodeContents(pA);
  sel().removeAllRanges(); sel().addRange(rq);
  doc.querySelector('[data-fmt="quote"]').click();
  check("blockquote создан вокруг первого блока", !!editor.querySelector("blockquote"),
    editor.innerHTML);
  check("markdown '> ' только у первой строки",
    bodyEl.value.startsWith("> Первый абзац."), JSON.stringify(bodyEl.value));
  doc.querySelector('[data-fmt="quote"]').click();
  check("цитата снята", !editor.querySelector("blockquote"), editor.innerHTML);

  // --- жирный на выделении внутри абзаца ---
  const pW = Array.from(editor.children).find(el => el.textContent.includes("Второй"));
  const rt = doc.createRange();
  rt.setStart(pW.firstChild, 0); rt.setEnd(pW.firstChild, 6);
  sel().removeAllRanges(); sel().addRange(rt);
  doc.querySelector('[data-fmt="bold"]').click();
  check("выделение обернуто в <strong>", !!pW.querySelector("strong"), pW.innerHTML);
  check("markdown ** вокруг выделения", bodyEl.value.includes("**Второй**"),
    JSON.stringify(bodyEl.value));

  // --- HR ---
  const lastP = Array.from(editor.children).filter(el => el.tagName === "P").pop();
  const rh = doc.createRange();
  const lt = lastP.firstChild;
  rh.setStart(lt, Math.min(7, lt.textContent.length)); rh.collapse(true);
  sel().removeAllRanges(); sel().addRange(rh);
  doc.querySelector('[data-fmt="hr"]').click();
  check("hr вставлен", !!editor.querySelector("hr"), editor.innerHTML);
  check("markdown содержит ---", bodyEl.value.includes("---"), JSON.stringify(bodyEl.value));
  check("весь текст сохранён", ["Первый","Второй","Третий"].every(w => bodyEl.value.includes(w)),
    JSON.stringify(bodyEl.value));

  check("нет zero-width пробелов после операций", !editor.innerHTML.includes("\u200b"),
    JSON.stringify(editor.innerHTML));

  console.log("FINAL MARKDOWN:", JSON.stringify(bodyEl.value));
  console.log(fails ? "RESULT: " + fails + " FAILS" : "RESULT: ALL OK");
  process.exit(fails ? 1 : 0);
}, 100);
