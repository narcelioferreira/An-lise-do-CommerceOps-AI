// Gráficos em SVG puro para o painel e os cartões. Cores vêm das classes CSS de cada página.
(function () {
  const nf = (d) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: d, minimumFractionDigits: d });
  const fmt = {
    int: (v) => nf(0).format(v),
    pct: (v, d = 1) => nf(d).format(v * 100) + "%",
    brl: (v) => "R$ " + nf(2).format(v),
    mi: (v) => "R$ " + nf(1).format(v / 1e6) + " mi",
    mil: (v) => nf(0).format(v / 1000) + " mil",
    dec: (v, d = 2) => nf(d).format(v),
  };
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const mes = (s) => MESES[+s.slice(5, 7) - 1] + "/" + s.slice(2, 4);
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

  function ticks(max, n = 4) {
    const raw = max / n;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw);
    const out = [];
    for (let v = 0; v <= max + step * 0.001; v += step) out.push(v);
    if (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
    return out;
  }

  // Barra com a ponta de dados arredondada (4px) e a base reta no eixo.
  function barV(x, y, w, h, r = 4) {
    r = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  function barH(x, y, w, h, r = 4) {
    r = Math.min(r, h / 2, w);
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }

  // Colunas verticais: dados [{rotulo, valor, tip, destaque}]
  function colunas(el, o) {
    const W = o.largura || el.clientWidth, H = o.altura || 240;
    const m = { t: 16, r: 8, b: o.margemInf || 26, l: o.margemEsq || 44 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const tk = ticks(Math.max(...o.dados.map((d) => d.valor)));
    const max = tk[tk.length - 1];
    const bw = iw / o.dados.length, gap = Math.max(2, bw * 0.22);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(o.titulo || "")}">`;
    for (const t of tk) {
      const y = m.t + ih - (t / max) * ih;
      s += `<line class="grade" x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}"/>`;
      s += `<text class="eixo" x="${m.l - 6}" y="${y + 4}" text-anchor="end">${o.fmtEixo(t)}</text>`;
    }
    o.dados.forEach((d, i) => {
      const h = (d.valor / max) * ih, x = m.l + i * bw + gap / 2, y = m.t + ih - h;
      s += `<path class="${d.destaque ? "marca-2" : "marca-1"}" d="${barV(x, y, bw - gap, h)}"/>`;
      s += `<rect class="alvo" x="${m.l + i * bw}" y="${m.t}" width="${bw}" height="${ih}" data-tip="${esc(d.tip)}"/>`;
      if (i % (o.passoRotulo || 1) === 0)
        s += `<text class="eixo" x="${x + (bw - gap) / 2}" y="${H - 6}" text-anchor="middle">${d.rotulo}</text>`;
      if (d.rotuloValor) s += `<text class="valor" x="${x + (bw - gap) / 2}" y="${y - 6}" text-anchor="middle">${d.rotuloValor}</text>`;
    });
    el.innerHTML = s + "</svg>";
  }

  // Linha com área: dados [{rotulo, valor, tip, destaque}]; ref = linha de referência {valor, rotulo}
  function linha(el, o) {
    const W = o.largura || el.clientWidth, H = o.altura || 240;
    const m = { t: 20, r: 12, b: o.margemInf || 26, l: o.margemEsq || 44 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const tk = ticks(Math.max(...o.dados.map((d) => d.valor)));
    const max = tk[tk.length - 1];
    const px = (i) => m.l + (i / (o.dados.length - 1)) * iw, py = (v) => m.t + ih - (v / max) * ih;
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(o.titulo || "")}">`;
    for (const t of tk) {
      s += `<line class="grade" x1="${m.l}" x2="${W - m.r}" y1="${py(t)}" y2="${py(t)}"/>`;
      s += `<text class="eixo" x="${m.l - 6}" y="${py(t) + 4}" text-anchor="end">${o.fmtEixo(t)}</text>`;
    }
    if (o.ref) {
      s += `<line class="ref" x1="${m.l}" x2="${W - m.r}" y1="${py(o.ref.valor)}" y2="${py(o.ref.valor)}"/>`;
      s += `<text class="eixo" x="${m.l + 4}" y="${py(o.ref.valor) - 6}">${o.ref.rotulo}</text>`;
    }
    const pts = o.dados.map((d, i) => `${px(i)},${py(d.valor)}`);
    s += `<path class="area" d="M${px(0)},${py(0)}L${pts.join("L")}L${px(o.dados.length - 1)},${py(0)}Z"/>`;
    s += `<path class="traco" d="M${pts.join("L")}"/>`;
    const bw = iw / (o.dados.length - 1);
    o.dados.forEach((d, i) => {
      if (d.destaque) {
        s += `<circle class="ponto" cx="${px(i)}" cy="${py(d.valor)}" r="5"/>`;
        const anc = i > o.dados.length * 0.75 ? "end" : "middle";
        s += `<text class="valor" x="${px(i)}" y="${py(d.valor) - 11}" text-anchor="${anc}">${d.rotuloValor}</text>`;
      }
      if (i % (o.passoRotulo || 1) === 0)
        s += `<text class="eixo" x="${px(i)}" y="${H - 8}" text-anchor="middle">${d.rotulo}</text>`;
      s += `<rect class="alvo" x="${px(i) - bw / 2}" y="${m.t}" width="${bw}" height="${ih}" data-tip="${esc(d.tip)}"/>`;
    });
    el.innerHTML = s + "</svg>";
  }

  // Barras horizontais: dados [{rotulo, valor, texto, tip, destaque}]
  function barras(el, o) {
    const W = o.largura || el.clientWidth;
    const lh = o.linha || 30, bh = o.espessura || 16;
    const m = { t: 4, r: o.margemDir || 64, b: o.ref ? 22 : 4, l: o.margemEsq || 120 };
    const H = m.t + m.b + lh * o.dados.length, iw = W - m.l - m.r;
    const max = o.max || Math.max(...o.dados.map((d) => d.valor));
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(o.titulo || "")}">`;
    o.dados.forEach((d, i) => {
      const y = m.t + i * lh, w = Math.max(2, (d.valor / max) * iw);
      s += `<text class="rotulo" x="${m.l - 10}" y="${y + lh / 2 + 4}" text-anchor="end">${d.rotulo}</text>`;
      s += `<path class="${d.destaque ? "marca-2" : "marca-1"}" d="${barH(m.l, y + (lh - bh) / 2, w, bh)}"/>`;
      s += `<text class="valor" x="${m.l + w + 8}" y="${y + lh / 2 + 4}">${d.texto}</text>`;
      s += `<rect class="alvo" x="0" y="${y}" width="${W}" height="${lh}" data-tip="${esc(d.tip || d.rotulo + ": " + d.texto)}"/>`;
    });
    if (o.ref) {
      const x = m.l + (o.ref.valor / max) * iw;
      s += `<line class="ref" x1="${x}" x2="${x}" y1="${m.t}" y2="${H - m.b + 4}"/>`;
      s += `<text class="eixo" x="${x}" y="${H - 4}" text-anchor="middle">${o.ref.rotulo}</text>`;
    }
    el.innerHTML = s + "</svg>";
  }

  function dica() {
    const tip = document.createElement("div");
    tip.className = "dica";
    tip.hidden = true;
    document.body.appendChild(tip);
    document.addEventListener("pointermove", (e) => {
      const t = e.target.closest && e.target.closest("[data-tip]");
      if (!t) return void (tip.hidden = true);
      tip.textContent = t.dataset.tip;
      tip.hidden = false;
      const r = tip.getBoundingClientRect();
      tip.style.left = Math.min(e.clientX + 14, innerWidth - r.width - 8) + "px";
      tip.style.top = Math.max(8, e.clientY - r.height - 10) + "px";
    });
  }

  const CATEGORIAS = {
    beleza_saude: "Beleza e saúde", relogios_presentes: "Relógios e presentes",
    cama_mesa_banho: "Cama, mesa e banho", esporte_lazer: "Esporte e lazer",
    informatica_acessorios: "Informática", moveis_decoracao: "Móveis e decoração",
    utilidades_domesticas: "Utilidades domésticas", cool_stuff: "Cool stuff",
    automotivo: "Automotivo", ferramentas_jardim: "Ferramentas e jardim",
  };
  const PAGAMENTOS = { credit_card: "Cartão de crédito", boleto: "Boleto", voucher: "Voucher", debit_card: "Cartão de débito" };
  const FAIXAS = { no_prazo: "No prazo", ate_5d: "Até 5 dias de atraso", mais_5d: "Mais de 5 dias de atraso" };
  const ACOES = {
    "ocorrencia:atraso_entrega": "Ocorrência de atraso aberta",
    "ocorrencia:defeito_produto": "Ocorrência de defeito aberta",
    devolucao: "Devolução registrada",
  };

  window.G = { fmt, mes, esc, colunas, linha, barras, dica, CATEGORIAS, PAGAMENTOS, FAIXAS, ACOES };
})();
