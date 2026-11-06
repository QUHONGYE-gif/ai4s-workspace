/* Project entry page: scroll reveals, the tagline word reveal, the reuse pipeline
   explanation and the member entry. Nothing here talks to the workbench API. */
(() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const memberKey = 'yanxu-demo-member';

  // Sections rise into place once, when they first enter the viewport.
  const revealSections = function revealSections() {
    const items = document.querySelectorAll('.reveal');
    if (reducedMotion || !('IntersectionObserver' in window)) {
      items.forEach((item) => item.classList.add('is-visible'));
      return;
    }
    // Items that share a row come in one after another.
    document.querySelectorAll('.pain-list, .question-grid, .scene-grid, .layers').forEach((grid) => {
      [...grid.children].forEach((child, index) => child.style.setProperty('--delay', index * 80 + 'ms'));
    });
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.18, rootMargin: '0px 0px -40px 0px' },
    );
    items.forEach((item) => observer.observe(item));
  };

  // Each word of the tagline lights up as it crosses a line at 65% of the viewport height.
  const revealTagline = function revealTagline() {
    const text = document.querySelector('[data-words]');
    if (!text) return;
    const parts = text.innerHTML.split(/(<br>)/);
    text.innerHTML = parts
      .map((part) =>
        part === '<br>'
          ? part
          : Array.from(part)
              .map((char) => `<span class="word">${char}</span>`)
              .join(''),
      )
      .join('');
    const words = [...text.querySelectorAll('.word')];
    if (reducedMotion) {
      words.forEach((word) => word.classList.add('is-on'));
      return;
    }
    let scheduled = false;
    const update = function update() {
      scheduled = false;
      const box = text.getBoundingClientRect();
      const line = window.innerHeight * 0.65;
      const progress = Math.min(1, Math.max(0, (line - box.top) / Math.max(1, box.height)));
      const lit = Math.round(progress * words.length);
      words.forEach((word, index) => word.classList.toggle('is-on', index < lit));
    };
    window.addEventListener(
      'scroll',
      () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(update);
      },
      { passive: true },
    );
    update();
  };

  // The hero image drifts slower than the page; the nav turns light after the hero.
  const followScroll = function followScroll() {
    const nav = document.querySelector('[data-nav]');
    const media = document.querySelector('[data-parallax]');
    const hero = document.querySelector('.hero');
    let scheduled = false;
    const update = function update() {
      scheduled = false;
      const y = window.scrollY;
      nav.classList.toggle('is-light', y > hero.offsetHeight - 80);
      if (media && !reducedMotion && y < hero.offsetHeight) media.style.transform = `translateY(${y * 0.25}px)`;
    };
    window.addEventListener(
      'scroll',
      () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(update);
      },
      { passive: true },
    );
    update();
  };

  // Mark the nav link of the section in view.
  const trackSections = function trackSections() {
    const links = [...document.querySelectorAll('.nav-links a')];
    if (!('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          links.forEach((link) => {
            if (link.hash === '#' + entry.target.id) link.setAttribute('aria-current', 'true');
            else link.removeAttribute('aria-current');
          });
        });
      },
      { rootMargin: '-45% 0px -50% 0px' },
    );
    links.forEach((link) => {
      const section = document.querySelector(link.hash);
      if (section) observer.observe(section);
    });
    // Back on the hero, no section link is current.
    observer.observe(document.querySelector('#top'));
  };

  const bindMenu = function bindMenu() {
    const nav = document.querySelector('[data-nav]');
    const toggle = document.querySelector('[data-nav-toggle]');
    const setOpen = function setOpen(open) {
      nav.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? '关闭目录' : '打开目录');
    };
    toggle.addEventListener('click', () => setOpen(!nav.classList.contains('is-open')));
    nav.querySelectorAll('.nav-links a').forEach((link) => link.addEventListener('click', () => setOpen(false)));
  };

  // Changing one stage keeps everything upstream and marks everything downstream for recompute.
  // MMseqs2 searches homologs for the designed sequences, so it sits downstream of ProteinMPNN.
  const explainPipeline = function explainPipeline() {
    const stages = [...document.querySelectorAll('[data-stage]')];
    const summary = document.querySelector('[data-summary]');
    const chips = [...document.querySelectorAll('[data-change]')];
    const names = stages.map((stage) => stage.querySelector('strong').textContent);
    const meterReuse = document.querySelector('[data-meter-reuse]');
    const meterCompute = document.querySelector('[data-meter-compute]');
    const show = function show(change) {
      const changed = change === 'none' ? -1 : Number(change);
      const reusedCount = changed < 0 ? stages.length : changed;
      meterReuse.style.width = (reusedCount / stages.length) * 100 + '%';
      meterCompute.style.width = ((stages.length - reusedCount) / stages.length) * 100 + '%';
      stages.forEach((stage, index) => {
        const state = stage.querySelector('.stage-state');
        stage.classList.toggle('is-changed', index === changed);
        stage.classList.toggle('is-stale', changed >= 0 && index > changed);
        state.textContent = changed < 0 || index < changed ? '直接复用' : index === changed ? '已修改 · 重算' : '依赖变化 · 重算';
      });
      chips.forEach((chip) => chip.setAttribute('aria-pressed', String(chip.dataset.change === change)));
      if (changed < 0) {
        summary.innerHTML = '生成条件都没变：<b>4 个步骤全部直接复用</b>已有结果，不再占用 GPU。';
      } else {
        const reused = names.slice(0, changed);
        summary.innerHTML = `修改 <b>${names[changed]}</b> 后，${
          reused.length ? `<b>${reused.join('、')}</b> 直接复用；` : '没有上游结果可以复用；'
        }<b>${names.slice(changed).join('、')}</b> 需要重新计算。`;
      }
    };
    chips.forEach((chip) => chip.addEventListener('click', () => show(chip.dataset.change)));
    show('none');

    // The light on the rail travels the full rail width at any screen size.
    const pipeline = document.querySelector('[data-pipeline]');
    const measure = () => pipeline.style.setProperty('--rail', pipeline.offsetWidth * 0.84 + 'px');
    window.addEventListener('resize', measure, { passive: true });
    measure();
  };

  // Selecting a node in the lineage graph shows its identity and relations.
  const explainLineage = function explainLineage() {
    const facts = {
      e01: ['RFdiffusion 运行 E01', '生成运行 · 成员甲', '骨架生成条件与随机种子', '骨架 B1'],
      b1: ['骨架 B1', '科学产物 · PDB', 'RFdiffusion 运行 E01', 'ProteinMPNN 运行 E02、E03'],
      e02: ['ProteinMPNN 运行 E02', '序列设计 · 成员甲', '骨架 B1', '序列 S1'],
      e03: ['ProteinMPNN 运行 E03', '序列设计 · 成员乙', '骨架 B1', '序列 S2'],
      s1: ['序列 S1', '科学产物 · FASTA', 'ProteinMPNN 运行 E02', 'Boltz-2 结构预测'],
      s2: ['序列 S2', '科学产物 · FASTA', 'ProteinMPNN 运行 E03', '可供后续实验复用'],
    };
    const nodes = [...document.querySelectorAll('[data-node]')];
    const fields = ['title', 'kind', 'from', 'to'].map((name) => document.querySelector(`[data-field="${name}"]`));
    const select = function select(node) {
      nodes.forEach((item) => item.classList.toggle('is-selected', item === node));
      facts[node.dataset.node].forEach((value, index) => {
        fields[index].textContent = value;
      });
    };
    nodes.forEach((node) => {
      node.addEventListener('click', () => select(node));
      node.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          select(node);
        }
      });
    });
  };

  // The entry keeps only a display name in this browser; there is no password and no account.
  const bindEntry = function bindEntry() {
    const form = document.querySelector('[data-enter-form]');
    const input = form.querySelector('#member');
    const error = form.querySelector('[data-enter-error]');
    try {
      input.value = localStorage.getItem(memberKey) || '';
    } catch {
      // Storage may be blocked; the form still works for this visit.
    }
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const name = input.value.trim();
      if (!name) {
        error.textContent = '请填写显示名称，或以访客身份进入。';
        error.hidden = false;
        input.focus();
        return;
      }
      error.hidden = true;
      try {
        localStorage.setItem(memberKey, name);
      } catch {
        // Without storage the workbench shows the sample researcher.
      }
      location.href = './workbench.html';
    });
    input.addEventListener('input', () => {
      error.hidden = true;
    });
    form.querySelector('[data-guest]').addEventListener('click', () => {
      try {
        localStorage.removeItem(memberKey);
      } catch {
        // Nothing stored, nothing to clear.
      }
    });
  };

  revealSections();
  revealTagline();
  followScroll();
  trackSections();
  bindMenu();
  explainPipeline();
  explainLineage();
  bindEntry();
})();
