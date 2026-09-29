document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.remove('js-off');

    // 0. Ransom note набор букв: вырезки из разных «шрифтов и бумажек»
    //    Работает для элементов <span class="ransomify" data-ransom="ТЕКСТ">…</span>
    //    Без JS остаётся обычный текст (progressive enhancement).
    const RN_CLASSES = ['rn-a', 'rn-b', 'rn-c3', 'rn-d', 'rn-e', 'rn-f', 'rn-g', 'rn-h'];

    // Детерминированный ГПСЧ из строки — набор букв не «прыгает» между рендерами
    function rnRand(seedStr) {
        let seed = 0;
        for (let i = 0; i < seedStr.length; i++) seed = (seed * 31 + seedStr.charCodeAt(i)) >>> 0;
        return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    }

    // Лоскут бумаги с целым словом (как в logo-стиле: «Archive» одной вырезкой)
    function rnPatch(text, cls, rotateDeg) {
        const s = document.createElement('span');
        s.className = 'rn-patch' + (cls ? ' ' + cls : '');
        if (typeof rotateDeg === 'number') s.style.setProperty('--rot', rotateDeg.toFixed(2) + 'deg');
        s.textContent = text;
        return s;
    }

    function buildRansom(el) {
        const text = el.getAttribute('data-ransom') || el.textContent;
        if (!text.trim()) return;
        const rand = rnRand(text);

        el.textContent = '';
        const words = text.split(/\s+/).filter(Boolean);
        words.forEach((word, wi) => {
            const w = document.createElement('span');
            w.className = 'rn-word';
            for (const ch of word) {
                const c = document.createElement('span');
                c.className = 'rn-c ' + RN_CLASSES[Math.floor(rand() * RN_CLASSES.length)];
                c.textContent = ch;
                w.appendChild(c);
            }
            el.appendChild(w);
            if (wi < words.length - 1) el.appendChild(document.createTextNode(' '));
        });
    }

    // Логотип «Gigs Archive»: первые 4 буквы — отдельные вырезки (G i g s),
    // а всё слово «Archive» — один общий лоскуток бумаги.
    function buildLogoRansom(el) {
        const parts = [
            { t: 'G', patch: false },
            { t: 'i', patch: false },
            { t: 'g', patch: false },
            { t: 's', patch: false },
            { t: 'Archive', patch: true },
        ];
        el.textContent = '';
        const rand = rnRand('logo:' + parts.map(p => p.t).join(''));
        parts.forEach((p, i) => {
            if (p.patch) {
                el.appendChild(rnPatch(p.t, 'rn-logo-word'));
            } else {
                const wrap = document.createElement('span');
                wrap.className = 'rn-logo-letter';
                const rot = (rand() * 12 - 6);
                wrap.style.setProperty('--rot', rot.toFixed(2) + 'deg');
                const inner = document.createElement('span');
                inner.className = 'rn-c ' + RN_CLASSES[Math.floor(rand() * RN_CLASSES.length)] + ' rn-logo-ch';
                inner.textContent = p.t;
                wrap.appendChild(inner);
                el.appendChild(wrap);
            }
            if (i < parts.length - 1 && p.patch === false && parts[i + 1].patch) {
                el.appendChild(document.createTextNode(' '));
            }
        });
    }

    document.querySelectorAll('.ransomify').forEach(buildRansom);
    document.querySelectorAll('.ransomify-logo').forEach(buildLogoRansom);

    // 0b. «Тонировка» вырезок палитрой конкретной афиши (killer feature).
    //     Берём <img data-tint>, рисуем её на маленьком canvas, получаем
    //     доминирующие цвета и красим paper/ink каждой буквы заголовка в тон
    //     постера. Canvas может быть «грязным» из-за CORS — тогда молча
    //     оставляем стандартную бумажную палитру сайта.
    const RN_TINT_CACHE = new Map(); // url -> [ {paper, ink}, ... ] | null

    function lum(r, g, b) { return 0.2126 * r + 0.7152 * g + 0.0722 * b; }

    function extractPalette(img) {
        try {
            const W = 48, H = 64;                       // афиша ~3:4, деталей не нужно
            const cv = document.createElement('canvas');
            cv.width = W; cv.height = H;
            const ctx = cv.getContext('2d', { willReadFrequently: true });
            ctx.drawImage(img, 0, 0, W, H);
            const data = ctx.getImageData(0, 0, W, H).data; // может бросить SecurityError (CORS)

            // Квантование до 4 бит на канал — группируем похожие оттенки
            const buckets = new Map();
            for (let i = 0; i < data.length; i += 4) {
                if (data[i + 3] < 128) continue;         // прозрачные пиксели
                const r = data[i], g = data[i + 1], b = data[i + 2];
                const key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
                let e = buckets.get(key);
                if (!e) { e = { n: 0, r: 0, g: 0, b: 0 }; buckets.set(key, e); }
                e.n++; e.r += r; e.g += g; e.b += b;
            }
            const sorted = [...buckets.values()].sort((a, b) => b.n - a.n);
            if (!sorted.length) return null;

            const out = [];
            for (const e of sorted) {
                const r = Math.round(e.r / e.n), g = Math.round(e.g / e.n), b = Math.round(e.b / e.n);
                const l = lum(r, g, b);
                if (l < 28 || l > 232) continue;         // почти чёрные/белые — это фон, не «краска»
                const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
                if (mx - mn < 24) continue;              // серости
                out.push({
                    paper: `rgb(${r}, ${g}, ${b})`,
                    ink: l > 140 ? 'rgb(12, 12, 18)' : 'rgb(248, 246, 236)',
                });
                if (out.length >= 6) break;
            }
            return out.length >= 2 ? out.slice(0, 5) : null;
        } catch (_) {
            return null;                                  // CORS / битая картинка — без тонировки
        }
    }

    function applyTint(card, pal) {
        const letters = card.querySelectorAll('.card-body h3 .rn-c, .detail-title .rn-c');
        if (!letters.length) return;
        const rand = rnRand('tint:' + (card.querySelector('[data-tint]')?.getAttribute('src') || ''));
        letters.forEach(c => {
            const p = pal[Math.floor(rand() * pal.length)];
            c.style.background = p.paper;
            c.style.color = p.ink;
        });
        card.classList.add('rn-tinted');
    }

    function tintCardFromPoster(card, img) {
        const url = img.getAttribute('src');
        if (RN_TINT_CACHE.has(url)) {
            if (RN_TINT_CACHE.get(url)) applyTint(card, RN_TINT_CACHE.get(url));
            return;
        }
        const run = () => {
            const pal = extractPalette(img);
            RN_TINT_CACHE.set(url, pal);
            if (pal) applyTint(card, pal);
        };
        if (img.complete && img.naturalWidth) run();
        else img.addEventListener('load', run, { once: true });
    }

    document.querySelectorAll('.poster-card, .poster-detail').forEach(card => {
        const img = card.querySelector('img[data-tint]');
        if (img) tintCardFromPoster(card, img);
    });

    // 1. Navbar scroll effect (только если есть navbar)
    const navbar = document.getElementById('navbar');
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) navbar.classList.add('scrolled');
            else navbar.classList.remove('scrolled');
        });
    }

    // 2. Mobile menu toggle
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const navLinks = document.getElementById('navLinks');
    if (mobileMenuBtn && navLinks) {
        mobileMenuBtn.addEventListener('click', () => navLinks.classList.toggle('active'));
        navLinks.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => navLinks.classList.remove('active'));
        });
    }
    // 2.5. Подсветка активной ссылки в навигации
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-links a').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    // 3. Scroll reveal animation (теперь ловит и .reveal, и стандартные .card)
    const revealElements = document.querySelectorAll('.reveal, .card, .event-card, .article-card');
    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1 });
    revealElements.forEach(el => revealObserver.observe(el));

    // 4. Counter animation
    function animateCounter(element, target, duration = 2000) {
        let start = 0;
        const increment = target / (duration / 16);
        const timer = setInterval(() => {
            start += increment;
            if (start >= target) {
                element.textContent = target;
                clearInterval(timer);
            } else {
                element.textContent = Math.floor(start);
            }
        }, 16);
    }

    const statsSection = document.querySelector('.hero-stats');
    if (statsSection) {
        const statsObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const counters = entry.target.querySelectorAll('.stat-number');
                    counters.forEach(counter => {
                        const target = parseInt(counter.getAttribute('data-target'), 10) || 0;
                        animateCounter(counter, target);
                    });
                    statsObserver.disconnect();
                }
            });
        }, { threshold: 0.5 });
        statsObserver.observe(statsSection);
    }

    // 5. Smooth scroll
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    // 6. Card hover tilt effect (только десктоп) — сдержанный «сдвиг вырезки»
    if (window.matchMedia("(min-width: 769px)").matches) {
        document.querySelectorAll('.event-card, .article-card, .card').forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                const rotateX = (y - centerY) / 90; // мягче:ransom-вырезка почти не «прыгает»
                const rotateY = (centerX - x) / 90;
                card.style.transform = `perspective(1200px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-5px)`;
            });
            card.addEventListener('mouseleave', () => { card.style.transform = ''; });
        });
    }
});