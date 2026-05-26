import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
NOTION_TOKEN       = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agencia MB Briefing Mensal - online"})

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.form.get("dados")
        if not raw:
            return jsonify({"erro": "Campo 'dados' não encontrado"}), 400

        dados = json.loads(raw)
        idioma = dados.get("idioma", "pt")

        p1 = dados.get("pagina1", {})
        p2 = dados.get("pagina2", {})
        p3 = dados.get("pagina3", {})
        p4 = dados.get("pagina4", {})

        nome_cliente = p1.get("nomeCliente", "Cliente")
        hoje = datetime.now().strftime("%d/%m/%Y")
        titulo_pagina = f"Briefing {nome_cliente} — {hoje}"

        # Traduzir se necessário
        dados_pt = None
        if idioma == "en":
            dados_pt = traduzir_para_portugues(dados)

        # Gerar diagnóstico (usando dados em pt se disponível)
        dados_diag = dados_pt if dados_pt else dados
        diagnostico = gerar_diagnostico(dados_diag, nome_cliente, "")

        # Salvar no Notion
        resultado = salvar_no_notion(
            titulo=titulo_pagina,
            dados_original=dados,
            dados_pt=dados_pt,
            diagnostico=diagnostico,
            idioma=idioma
        )

        return jsonify({"status": "ok", "notion": resultado}), 200

    except Exception as e:
        print(f"[ERRO WEBHOOK] {e}")
        return jsonify({"erro": str(e)}), 500


def groq_call(prompt, max_tokens=2000):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=60,
        )
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erro: {e}]"


def traduzir_para_portugues(dados):
    """Traduz todos os campos de texto do briefing em inglês para português."""
    p1 = dados.get("pagina1", {})
    p2 = dados.get("pagina2", {})
    p3 = dados.get("pagina3", {})
    p4 = dados.get("pagina4", {})

    campos = {
        "obsGravacao": p1.get("obsGravacao",""),
        "canais": p2.get("canais",""),
        "melhorCanal": p2.get("melhorCanal",""),
        "objecoes": p2.get("objecoes",""),
        "naoFechamentos": p2.get("naoFechamentos",""),
        "descricaoOferta": p2.get("descricaoOferta",""),
        "historiasMes": p3.get("historiasMes",""),
        "resultadosClientes": p3.get("resultadosClientes",""),
        "produtosDestaque": p3.get("produtosDestaque",""),
        "novidades": p3.get("novidades",""),
        "temas": p3.get("temas",""),
        "obsFinal": p3.get("obsFinal",""),
        "historia": p4.get("historia",""),
        "publicoAlvo": p4.get("publicoAlvo",""),
        "naoAcredita": p4.get("naoAcredita",""),
        "diferencial": p4.get("diferencial",""),
        "datasImportantes": p4.get("datasImportantes",""),
        "tomVozDesc": p4.get("tomVozDesc",""),
    }

    # Filtrar campos não vazios
    campos_preenchidos = {k: v for k, v in campos.items() if v.strip()}
    if not campos_preenchidos:
        return dados

    prompt = f"""Traduza os seguintes textos do inglês para o português brasileiro de forma natural e fluida.
Retorne APENAS um JSON válido com as mesmas chaves, sem explicações, sem markdown.

{json.dumps(campos_preenchidos, ensure_ascii=False)}"""

    resultado_str = groq_call(prompt, max_tokens=1500)

    try:
        # Limpar possível markdown
        resultado_str = resultado_str.strip()
        if resultado_str.startswith("```"):
            resultado_str = resultado_str.split("```")[1]
            if resultado_str.startswith("json"):
                resultado_str = resultado_str[4:]
        traducao = json.loads(resultado_str.strip())
    except:
        return None

    # Montar dados_pt com traduções
    import copy
    dados_pt = copy.deepcopy(dados)
    dados_pt["pagina1"]["obsGravacao"] = traducao.get("obsGravacao", p1.get("obsGravacao",""))
    dados_pt["pagina2"]["canais"] = traducao.get("canais", p2.get("canais",""))
    dados_pt["pagina2"]["melhorCanal"] = traducao.get("melhorCanal", p2.get("melhorCanal",""))
    dados_pt["pagina2"]["objecoes"] = traducao.get("objecoes", p2.get("objecoes",""))
    dados_pt["pagina2"]["naoFechamentos"] = traducao.get("naoFechamentos", p2.get("naoFechamentos",""))
    dados_pt["pagina2"]["descricaoOferta"] = traducao.get("descricaoOferta", p2.get("descricaoOferta",""))
    dados_pt["pagina3"]["historiasMes"] = traducao.get("historiasMes", p3.get("historiasMes",""))
    dados_pt["pagina3"]["resultadosClientes"] = traducao.get("resultadosClientes", p3.get("resultadosClientes",""))
    dados_pt["pagina3"]["produtosDestaque"] = traducao.get("produtosDestaque", p3.get("produtosDestaque",""))
    dados_pt["pagina3"]["novidades"] = traducao.get("novidades", p3.get("novidades",""))
    dados_pt["pagina3"]["temas"] = traducao.get("temas", p3.get("temas",""))
    dados_pt["pagina3"]["obsFinal"] = traducao.get("obsFinal", p3.get("obsFinal",""))
    dados_pt["pagina4"]["historia"] = traducao.get("historia", p4.get("historia",""))
    dados_pt["pagina4"]["publicoAlvo"] = traducao.get("publicoAlvo", p4.get("publicoAlvo",""))
    dados_pt["pagina4"]["naoAcredita"] = traducao.get("naoAcredita", p4.get("naoAcredita",""))
    dados_pt["pagina4"]["diferencial"] = traducao.get("diferencial", p4.get("diferencial",""))
    dados_pt["pagina4"]["datasImportantes"] = traducao.get("datasImportantes", p4.get("datasImportantes",""))
    dados_pt["pagina4"]["tomVozDesc"] = traducao.get("tomVozDesc", p4.get("tomVozDesc",""))

    return dados_pt


def gerar_diagnostico(dados, nome, mes):
    p2 = dados.get("pagina2", {})
    p3 = dados.get("pagina3", {})
    p4 = dados.get("pagina4", {})

    prompt = f"""Você é um consultor estratégico de conteúdo digital especializado em profissionais de saúde e estética.
Analise o briefing mensal do cliente abaixo e gere um diagnóstico estratégico completo em português, estruturado em 6 seções.

CLIENTE: {nome}

DADOS COMERCIAIS:
- Canais: {p2.get('canais', p2.get('funis','não informado'))}
- Melhor canal: {p2.get('melhorCanal', p2.get('melhorFunil','não informado'))}
- Objeções: {p2.get('objecoes','não informado')}
- Não fechamentos: {p2.get('naoFechamentos','não informado')}
- Oferta: {p2.get('descricaoOferta','não informado')}

CONTEÚDO:
- Histórias: {p3.get('historiasMes','não informado')}
- Resultados de clientes: {p3.get('resultadosClientes','não informado')}
- Temas: {p3.get('temas','não informado')}

POSICIONAMENTO:
- História: {p4.get('historia','não informado')}
- Público: {p4.get('publicoAlvo','não informado')}
- Diferencial: {p4.get('diferencial','não informado')}
- Tom de voz: {p4.get('tomVoz','5')}/10

Gere o diagnóstico em 6 seções:
## 1. Visão Geral do Mês
## 2. Análise Comercial
## 3. Pontos Fortes
## 4. Desafios e Oportunidades
## 5. Recomendações de Conteúdo
## 6. Próximos Passos Prioritários"""

    return groq_call(prompt, max_tokens=1500)


def salvar_no_notion(titulo, dados_original, dados_pt, diagnostico, idioma):
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    p1o = dados_original.get("pagina1", {})
    p2o = dados_original.get("pagina2", {})
    p3o = dados_original.get("pagina3", {})
    p4o = dados_original.get("pagina4", {})

    blocos = []

    def h2(texto): return {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":texto}}]}}
    def h3(texto): return {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":texto}}]}}
    def p(texto): return {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":str(texto) if texto else "—"}}]}}
    def li(label, valor): return {"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":f"{label}: {valor if valor else '—'}"}}]}}
    def div(): return {"object":"block","type":"divider","divider":{}}
    def callout(texto, emoji="🇬🇧"):
        return {"object":"block","type":"callout","callout":{"rich_text":[{"type":"text","text":{"content":texto}}],"icon":{"emoji":emoji}}}

    # ── VERSÃO ORIGINAL (inglês se for en) ──────────────
    if idioma == "en":
        blocos.append(h2("🇬🇧 Original Responses (English)"))
        blocos.append(li("Can record", p1o.get("podeGravar","")))
        blocos.append(li("Materials", ", ".join(p1o.get("materiais",[]))))
        blocos.append(li("Preferred date", f"Day {p1o.get('dataGravacao','')}"))
        if p1o.get("obsGravacao"): blocos.append(li("Recording notes", p1o.get("obsGravacao","")))
        blocos.append(li("Channels", p2o.get("canais","")))
        blocos.append(li("Best channel", p2o.get("melhorCanal","")))
        blocos.append(li("Hesitations", p2o.get("objecoes","")))
        blocos.append(li("Why didn't commit", p2o.get("naoFechamentos","")))
        blocos.append(li("Offer", p2o.get("descricaoOferta","")))
        blocos.append(li("Stories", p3o.get("historiasMes","")))
        blocos.append(li("Client results", p3o.get("resultadosClientes","")))
        blocos.append(li("Highlights", p3o.get("produtosDestaque","")))
        blocos.append(li("News", p3o.get("novidades","")))
        blocos.append(li("Topics", p3o.get("temas","")))
        blocos.append(li("Background", p4o.get("historia","")))
        blocos.append(li("Target audience", p4o.get("publicoAlvo","")))
        blocos.append(li("Differentiator", p4o.get("diferencial","")))
        blocos.append(li("Tone of voice", f"{p4o.get('tomVoz','5')}/10 — {p4o.get('tomVozDesc','')}"))
        blocos.append(div())

    # ── VERSÃO EM PORTUGUÊS ──────────────────────────────
    pd = dados_pt if dados_pt else dados_original
    p1 = pd.get("pagina1", {})
    p2 = pd.get("pagina2", {})
    p3 = pd.get("pagina3", {})
    p4 = pd.get("pagina4", {})

    label_secao = "🇧🇷 Tradução para o Português" if idioma == "en" else "📋 Identificação e Gravação"

    blocos.append(h2(label_secao if idioma == "en" else "📋 Identificação e Gravação"))

    if idioma != "en":
        blocos.append(li("Cliente", p1.get("nomeCliente","")))
    blocos.append(li("Pode gravar", p1.get("podeGravar","")))
    mat = p1.get("materiais",[])
    blocos.append(li("Materiais", ", ".join(mat) if mat else "—"))
    blocos.append(li("Data preferida", f"Dia {p1.get('dataGravacao','')}"))
    if p1.get("obsGravacao"): blocos.append(li("Obs. gravação", p1.get("obsGravacao","")))
    blocos.append(div())

    blocos.append(h2("💰 Resultados Comerciais"))
    blocos.append(li("Canais", p2.get("canais", p2.get("funis",""))))
    blocos.append(li("Melhor canal", p2.get("melhorCanal", p2.get("melhorFunil",""))))
    blocos.append(li("Objeções", p2.get("objecoes","")))
    blocos.append(li("Não fechamentos", p2.get("naoFechamentos","")))
    if p2.get("descricaoOferta"):
        blocos.append(h3("Serviços / Produtos"))
        blocos.append(p(p2.get("descricaoOferta","")))
    if p2.get("playlist"): blocos.append(li("Playlist", p2.get("playlist","")))
    blocos.append(div())

    blocos.append(h2("🎬 Histórias e Conteúdo"))
    blocos.append(li("Histórias do mês", p3.get("historiasMes","")))
    blocos.append(li("Resultados de clientes", p3.get("resultadosClientes","")))
    blocos.append(li("Em destaque", p3.get("produtosDestaque","")))
    blocos.append(li("Novidades", p3.get("novidades","")))
    blocos.append(li("Temas", p3.get("temas","")))
    links = p3.get("links",[])
    if links:
        blocos.append(h3("Links de referência"))
        for lk in links:
            if lk: blocos.append(p(lk))
    if p3.get("obsFinal"): blocos.append(li("Obs. finais", p3.get("obsFinal","")))
    blocos.append(div())

    blocos.append(h2("🏢 Negócio e Posicionamento"))
    blocos.append(h3("História"))
    blocos.append(p(p4.get("historia","")))
    blocos.append(li("Público-alvo", p4.get("publicoAlvo","")))
    blocos.append(li("Não acredita em", p4.get("naoAcredita","")))
    blocos.append(li("Diferencial", p4.get("diferencial","")))
    blocos.append(li("Datas importantes", p4.get("datasImportantes","")))
    tom = p4.get("tomVoz","5")
    blocos.append(li("Tom de voz", f"{tom}/10"))
    if p4.get("tomVozDesc"): blocos.append(p(p4.get("tomVozDesc","")))
    blocos.append(div())

    # ── DIAGNÓSTICO ──────────────────────────────────────
    blocos.append(h2("🤖 Diagnóstico Estratégico — IA"))
    for linha in diagnostico.split("\n"):
        linha = linha.strip()
        if not linha: continue
        if linha.startswith("## "):
            blocos.append(h3(linha.replace("## ","")))
        elif len(linha) <= 2000:
            blocos.append(p(linha))
        else:
            for i in range(0,len(linha),2000):
                blocos.append(p(linha[i:i+2000]))

    # ── Criar página no Notion ───────────────────────────
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"emoji": "🇬🇧" if idioma == "en" else "📬"},
        "properties": {
            "Briefing": {"title": [{"text": {"content": titulo}}]},
            "Dia Recebido": {"date": {"start": hoje_iso}},
            "Status": {"select": {"name": "Não usado"}},
        },
        "children": blocos[:100],
    }

    r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=30)

    if r.status_code in (200, 201):
        page_id = r.json().get("id")
        if len(blocos) > 100:
            for i in range(100, len(blocos), 100):
                requests.patch(
                    f"https://api.notion.com/v1/blocks/{page_id}/children",
                    headers=NOTION_HEADERS, json={"children": blocos[i:i+100]}, timeout=30
                )
        return {"page_id": page_id}
    else:
        print(f"[ERRO NOTION] {r.status_code} — {r.text}")
        return {"erro": r.text}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
