document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.remove('js-off');

    // 0. Ransom note набор букв: вырезки из разных «шрифтов и бумажек»
    //    Работает для элементов <span class="ransomify" data-ransom="ТЕКСТ">…</span>
    //    Без JS остаётся обычный текст (progressive enhancement).
    const RN_CLASSES = ['rn-a', 'rn-b', 'rn-c3', 'rn-d', 'rn-e', 'rn-f', 'rn-g', 'rn-h'];
    function buildRansom(el) {
        const text = el.getAttribute('data-ransom') || el.textContent;
        if (!text.trim()) return;
        // Детерминированный seed из текста — набор не «прыгает» между рендерами
        let seed = 0;
        for (let i = 0; i < text.length; i++) seed = (seed * 31 + text.charCodeAt(i)) >>> 0;
        const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };

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
    document.querySelectorAll('.ransomify').forEach(buildRansom);

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