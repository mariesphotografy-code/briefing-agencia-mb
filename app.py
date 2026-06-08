import os, json, requests, copy
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

        # Detectar tipo de briefing
        tipo = detectar_tipo(dados)

        # Nome do cliente
        p1 = dados.get("pagina1", {})
        nome = p1.get("nomeCliente") or p1.get("nome") or "Cliente"
        hoje = datetime.now().strftime("%d/%m/%Y")
        prefixo = "Onboarding" if tipo == "onboarding" else "Briefing"
        titulo = f"{prefixo} {nome} — {hoje}"

        # Traduzir se inglês
        dados_pt = None
        if idioma == "en":
            dados_pt = traduzir(dados)

        # Diagnóstico (só para briefing mensal)
        diagnostico = None
        if tipo == "mensal":
            diagnostico = gerar_diagnostico(dados_pt or dados, nome)

        # Salvar no Notion
        resultado = salvar_no_notion(titulo, dados, dados_pt, diagnostico, tipo, idioma)
        return jsonify({"status": "ok", "notion": resultado}), 200

    except Exception as e:
        print(f"[ERRO] {e}")
        return jsonify({"erro": str(e)}), 500


def detectar_tipo(dados):
    """Detecta se é briefing mensal ou onboarding pelo número de páginas."""
    if "pagina5" in dados or "pagina6" in dados:
        return "onboarding"
    return "mensal"


def groq_call(prompt, max_tokens=2000, temp=0.5):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "temperature": temp},
            timeout=60,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erro IA: {e}]"


def traduzir(dados):
    """Traduz campos de texto do inglês para o português."""
    def extrair_textos(d, prefix=""):
        textos = {}
        for k, v in d.items():
            chave = f"{prefix}__{k}" if prefix else k
            if isinstance(v, str) and v.strip() and k != "idioma":
                textos[chave] = v
            elif isinstance(v, dict):
                textos.update(extrair_textos(v, k))
        return textos

    # Coletar todos os textos das páginas
    campos = {}
    for pg in ["pagina1","pagina2","pagina3","pagina4","pagina5","pagina6","pagina7","pagina8"]:
        if pg in dados:
            for k, v in dados[pg].items():
                if isinstance(v, str) and v.strip():
                    campos[f"{pg}||{k}"] = v

    if not campos:
        return None

    prompt = f"""Translate the following texts from English to Brazilian Portuguese naturally.
Return ONLY a valid JSON with the same keys. No markdown, no explanation.

{json.dumps(campos, ensure_ascii=False)}"""

    resultado = groq_call(prompt, max_tokens=2000, temp=0.2)
    try:
        resultado = resultado.strip()
        if "```" in resultado:
            resultado = resultado.split("```")[1]
            if resultado.startswith("json"):
                resultado = resultado[4:]
        traducao = json.loads(resultado.strip())
    except:
        return None

    dados_pt = copy.deepcopy(dados)
    for chave_composta, valor_traduzido in traducao.items():
        if "||" in chave_composta:
            pg, campo = chave_composta.split("||", 1)
            if pg in dados_pt and campo in dados_pt[pg]:
                dados_pt[pg][campo] = valor_traduzido
    return dados_pt


def gerar_diagnostico(dados, nome):
    p2 = dados.get("pagina2", {})
    p3 = dados.get("pagina3", {})
    p4 = dados.get("pagina4", {})
    prompt = f"""Você é um consultor estratégico de conteúdo digital.
Analise o briefing mensal do cliente {nome} e gere um diagnóstico em português em 6 seções:
## 1. Visão Geral do Mês
## 2. Análise Comercial
## 3. Pontos Fortes
## 4. Desafios e Oportunidades
## 5. Recomendações de Conteúdo
## 6. Próximos Passos

DADOS:
Canais: {p2.get('canais') or p2.get('funis','')}
Objeções: {p2.get('objecoes','')}
Histórias: {p3.get('historiasMes','')}
P�blico: {p4.get('publicoAlvo','')}
Diferencial: {p4.get('diferencial','')}"""
    return groq_call(prompt, max_tokens=1200)


# ── NOTION ────────────────────────────────────────────
def h2(t): return {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":t}}]}}
def h3(t): return {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":t}}]}}
def p(t):  return {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":str(t) if t else "—"}}]}}
def li(label, val): return {"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":f"{label}: {val if val else '—'}"}}]}}
def div(): return {"object":"block","type":"divider","divider":{}}


def blocos_mensal(dados):
    p1=dados.get("pagina1",{})
    p2=dados.get("pagina2",{})
    p3=dados.get("pagina3",{})
    p4=dados.get("pagina4",{})
    bl = []
    bl.append(h2("📋 Identificação"))
    bl.append(li("Cliente", p1.get("nomeCliente") or p1.get("nome","")))
    bl.append(li("Pode gravar", p1.get("podeGravar","")))
    mat = p1.get("materiais",[])
    bl.append(li("Materiais", ", ".join(mat) if mat else "—"))
    bl.append(li("Data preferida", f"Dia {p1.get('dataGravacao','')}" if p1.get("dataGravacao") else "—"))
    if p1.get("obsGravacao") or p1.get("obsGeral"): bl.append(li("Obs.", p1.get("obsGravacao") or p1.get("obsGeral","")))
    bl.append(div())

    bl.append(h2("💰 Resultados Comerciais"))
    bl.append(li("Canais", p2.get("canais") or p2.get("funis","")))
    bl.append(li("Melhor canal", p2.get("melhorCanal") or p2.get("melhorFunil","")))
    if p2.get("callsAgendadas"): bl.append(li("Consultas agendadas", p2.get("callsAgendadas","")))
    if p2.get("vendasFechadas"): bl.append(li("Vendas fechadas", p2.get("vendasFechadas","")))
    if p2.get("ticketMedio"):    bl.append(li("Ticket médio", f"R$ {p2.get('ticketMedio','')}"))
    if p2.get("taxaConversao"):  bl.append(li("Taxa de conversão", f"{p2.get('taxaConversao','')}%"))
    bl.append(li("Objeções", p2.get("objecoes","")))
    bl.append(li("Não fechamentos", p2.get("naoFechamentos","")))
    if p2.get("destaqueMes"): bl.append(li("Destaque do mês", p2.get("destaqueMes","")))
    if p2.get("descricaoOferta") or p2.get("servicos"):
        bl.append(h3("Serviços / Produtos"))
        bl.append(p(p2.get("descricaoOferta") or p2.get("servicos","")))
    if p2.get("elogios"):   bl.append(li("Elogios", p2.get("elogios","")))
    if p2.get("melhorias"): bl.append(li("Melhorias", p2.get("melhorias","")))
    if p2.get("playlist"):  bl.append(li("Playlist", p2.get("playlist","")))
    bl.append(div())

    bl.append(h2("🎬 Histórias e Conteúdo"))
    bl.append(li("Histórias", p3.get("historiasMes","")))
    bl.append(li("Resultados de clientes", p3.get("resultadosClientes") or p3.get("transformacoes","")))
    bl.append(li("Em destaque", p3.get("produtosDestaque") or p3.get("emDestaque","")))
    bl.append(li("Novidades", p3.get("novidades","")))
    bl.append(li("Temas", p3.get("temas","")))
    links = p3.get("links",[])
    if links:
        bl.append(h3("Links de referência"))
        for lk in links:
            if lk: bl.append(p(lk))
    if p3.get("obsFinal"): bl.append(li("Obs. finais", p3.get("obsFinal","")))
    bl.append(div())

    bl.append(h2("🏢 Negócio e Posicionamento"))
    bl.append(h3("História"))
    bl.append(p(p4.get("historia","")))
    bl.append(li("Público-alvo", p4.get("publicoAlvo","")))
    bl.append(li("Diferencial", p4.get("diferencial","")))
    if p4.get("naoAcredita"): bl.append(li("Não acredita em", p4.get("naoAcredita","")))
    if p4.get("datasImportantes") or p4.get("datas"): bl.append(li("Datas importantes", p4.get("datasImportantes") or p4.get("datas","")))
    bl.append(li("Tom de voz", f"{p4.get('tomVoz','5')}/10"))
    if p4.get("tomVozDesc"): bl.append(p(p4.get("tomVozDesc","")))
    # Campos barbearia
    if p4.get("sonho"): bl.append(li("Sonho", p4.get("sonho","")))
    return bl


def blocos_onboarding(dados):
    bl = []
    pgs = {f"pagina{i}": dados.get(f"pagina{i}",{}) for i in range(1,9)}

    p1=pgs["pagina1"]; p2=pgs["pagina2"]; p3=pgs["pagina3"]; p4=pgs["pagina4"]
    p5=pgs["pagina5"]; p6=pgs["pagina6"]; p7=pgs["pagina7"]; p8=pgs["pagina8"]

    bl.append(h2("👤 Identificação"))
    bl.append(li("Nome", p1.get("nome","")))
    bl.append(h3("Proposta de valor"))
    bl.append(p(p1.get("proposta","")))
    bl.append(div())

    bl.append(h2("🎵 Preferências Pessoais"))
    if p2.get("playlist"):  bl.append(li("Playlist", p2.get("playlist","")))
    if p2.get("youtube"):   bl.append(li("YouTube", p2.get("youtube","")))
    if p2.get("familia"):   bl.append(li("Família / Pets", p2.get("familia","")))
    if p2.get("adjetivos"): bl.append(li("Adjetivos", p2.get("adjetivos","")))
    if p2.get("pessoas"):   bl.append(li("Pessoas importantes", p2.get("pessoas","")))
    if p2.get("fatos"):     bl.append(h3("5 fatos aleatórios")); bl.append(p(p2.get("fatos","")))
    if p2.get("medo"):      bl.append(li("Maior medo", p2.get("medo","")))
    bl.append(div())

    bl.append(h2("💼 Trabalho & Negócio"))
    bl.append(h3("Como começou"))
    bl.append(p(p3.get("comeco","")))
    if p3.get("sonho"):       bl.append(li("Sonho de infância", p3.get("sonho","")))
    bl.append(h3("Público-alvo"))
    bl.append(p(p3.get("publico","")))
    if p3.get("naoAcredita"): bl.append(li("Não acredita em", p3.get("naoAcredita","")))
    if p3.get("diferencial"):  bl.append(li("Diferencial", p3.get("diferencial","")))
    bl.append(div())

    bl.append(h2("📱 Conteúdo & Redes Sociais"))
    if p4.get("assuntosSim"):   bl.append(li("Quer falar sobre", p4.get("assuntosSim","")))
    if p4.get("assuntosNao"):   bl.append(li("Jamais falaria", p4.get("assuntosNao","")))
    if p4.get("concorrentes"):  bl.append(li("Concorrentes", p4.get("concorrentes","")))
    if p4.get("perfisNicho"):   bl.append(li("Perfis do nicho que admira", p4.get("perfisNicho","")))
    if p4.get("perfisReels"):   bl.append(li("Perfis de reels que gosta", p4.get("perfisReels","")))
    if p4.get("perfisNao"):     bl.append(li("Não se identifica com", p4.get("perfisNao","")))
    if p4.get("deixaSeguir"):   bl.append(li("O que faz parar de seguir", p4.get("deixaSeguir","")))
    bl.append(div())

    bl.append(h2("📊 Perfil Próprio"))
    if p5.get("funciona"):    bl.append(li("O que funciona", p5.get("funciona","")))
    if p5.get("favoritos"):   bl.append(h3("Conteúdos favoritos")); bl.append(p(p5.get("favoritos","")))
    if p5.get("naoDaCerto"):  bl.append(li("O que não dá certo", p5.get("naoDaCerto","")))
    if p5.get("ensaio"):      bl.append(li("Ensaio fotográfico", p5.get("ensaio","")))
    if p5.get("redesSociais"):bl.append(li("Outras redes", p5.get("redesSociais","")))
    bl.append(div())

    bl.append(h2("🎯 Histórias, Objetivo & Serviços"))
    if p6.get("historias"):     bl.append(h3("Histórias dos últimos 3 anos")); bl.append(p(p6.get("historias","")))
    if p6.get("desejoPerfil"):  bl.append(li("Desejo com o perfil", p6.get("desejoPerfil","")))
    if p6.get("expectativa"):   bl.append(li("Expectativa da parceria", p6.get("expectativa","")))
    if p6.get("datasImportantes"): bl.append(li("Datas importantes", p6.get("datasImportantes","")))
    if p6.get("servicos"):      bl.append(h3("Serviços")); bl.append(p(p6.get("servicos","")))
    if p6.get("provasSociais"): bl.append(li("Provas sociais", p6.get("provasSociais","")))
    bl.append(div())

    bl.append(h2("🎨 Identidade Visual"))
    if p7.get("idVisual"):        bl.append(li("Identidade atual", p7.get("idVisual","")))
    if p7.get("artesAtuais"):     bl.append(li("Artes atuais", p7.get("artesAtuais","")))
    if p7.get("elementoIncluir"): bl.append(li("Quer incluir", p7.get("elementoIncluir","")))
    if p7.get("elementosVisuais"):bl.append(li("Gosta / evita", p7.get("elementosVisuais","")))
    if p7.get("perfisArte"):      bl.append(li("Perfis de arte", p7.get("perfisArte","")))
    if p7.get("corEvitar"):       bl.append(li("Cor a evitar", p7.get("corEvitar","")))
    if p7.get("universoMarca"):   bl.append(h3("Universo da marca")); bl.append(p(p7.get("universoMarca","")))
    bl.append(div())

    bl.append(h2("🗣️ Tom de Voz"))
    if p8.get("cumprimentos"):       bl.append(li("Cumprimentos", p8.get("cumprimentos","")))
    if p8.get("adjetivosPositivos"):  bl.append(li("Adjetivos positivos", p8.get("adjetivosPositivos","")))
    if p8.get("adjetivosNegativos"):  bl.append(li("Adjetivos negativos", p8.get("adjetivosNegativos","")))
    if p8.get("agressividade"):       bl.append(li("Nível de agressividade", f"{p8.get('agressividade','')}/10"))
    if p8.get("formalidade"):         bl.append(li("Nível de formalidade", f"{p8.get('formalidade','')}/10"))
    if p8.get("humor"):               bl.append(li("Nível de humor", f"{p8.get('humor','')}/10"))
    if p8.get("emojis"):              bl.append(li("Emojis", p8.get("emojis","")))
    return bl


def salvar_no_notion(titulo, dados_orig, dados_pt, diagnostico, tipo, idioma):
    hoje_iso = datetime.now().strftime("%Y-%m-%d")
    dados_usar = dados_pt if dados_pt else dados_orig
    emoji_icone = "📋" if tipo == "mensal" else "🧭"

    blocos = []

    # Versão original em inglês se necessário
    if idioma == "en" and dados_pt:
        blocos.append(h2("🇬🇧 Original Responses (English)"))
        for pg in ["pagina1","pagina2","pagina3","pagina4","pagina5","pagina6","pagina7","pagina8"]:
            sec = dados_orig.get(pg, {})
            if sec:
                for k, v in sec.items():
                    if v and str(v).strip() and k != "idioma":
                        blocos.append(li(k, str(v)))
        blocos.append(div())
        blocos.append(h2("🇧🇷 Tradução para o Português"))

    # Blocos principais
    if tipo == "onboarding":
        blocos += blocos_onboarding(dados_usar)
    else:
        blocos += blocos_mensal(dados_usar)

    # Diagnóstico (só mensal)
    if diagnostico:
        blocos.append(h2("🤖 Diagnóstico Estratégico — IA"))
        for linha in diagnostico.split("\n"):
            linha = linha.strip()
            if not linha: continue
            if linha.startswith("## "): blocos.append(h3(linha.replace("## ","")))
            elif len(linha) <= 2000: blocos.append(p(linha))
            else:
                for i in range(0, len(linha), 2000): blocos.append(p(linha[i:i+2000]))

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"emoji": emoji_icone},
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
        print(f"[ERRO NOTION] {r.status_code} — {r.text[:300]}")
        return {"erro": r.text[:300]}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
