import os, json, requests, copy
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
NOTION_TOKEN       = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

NOTION_HEADERS = {
    "Authorization": "Bearer " + (NOTION_TOKEN or ""),
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
            return jsonify({"erro": "Campo dados nao encontrado"}), 400
        dados = json.loads(raw)
        idioma = dados.get("idioma", "pt")
        tipo = "onboarding" if ("pagina5" in dados or "pagina6" in dados) else "mensal"
        p1 = dados.get("pagina1", {})
        nome = p1.get("nomeCliente") or p1.get("nome") or "Cliente"
        hoje = datetime.now().strftime("%d/%m/%Y")
        prefixo = "Onboarding" if tipo == "onboarding" else "Briefing"
        titulo = prefixo + " " + nome + " - " + hoje
        dados_pt = traduzir(dados) if idioma == "en" else None
        if tipo == "mensal":
            diagnostico = gerar_diagnostico(dados_pt or dados, nome)
        else:
            diagnostico = gerar_resumo_onboarding(dados_pt or dados, nome)
        resultado = salvar_no_notion(titulo, dados, dados_pt, diagnostico, tipo, idioma)
        return jsonify({"status": "ok", "notion": resultado}), 200
    except Exception as e:
        print("[ERRO] " + str(e))
        return jsonify({"erro": str(e)}), 500

def groq_call(prompt, max_tokens=2000):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + (GROQ_API_KEY or ""), "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "temperature": 0.5},
            timeout=60,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "[Erro IA: " + str(e) + "]"

def traduzir(dados):
    campos = {}
    for pg in ["pagina1","pagina2","pagina3","pagina4","pagina5","pagina6","pagina7","pagina8"]:
        if pg in dados:
            for k, v in dados[pg].items():
                if isinstance(v, str) and v.strip():
                    campos[pg + "||" + k] = v
    if not campos:
        return None
    prompt = "Translate from English to Brazilian Portuguese naturally. Return ONLY valid JSON with same keys, no markdown.\n\n" + json.dumps(campos, ensure_ascii=False)
    resultado = groq_call(prompt, max_tokens=2000)
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
    for chave, valor in traducao.items():
        if "||" in chave:
            pg, campo = chave.split("||", 1)
            if pg in dados_pt and campo in dados_pt[pg]:
                dados_pt[pg][campo] = valor
    return dados_pt

def gerar_diagnostico(dados, nome):
    p2 = dados.get("pagina2", {})
    p3 = dados.get("pagina3", {})
    p4 = dados.get("pagina4", {})
    prompt = (
        "Voce e um consultor estrategico de conteudo digital.\n"
        "Analise o briefing mensal do cliente " + nome + " e gere diagnostico em portugues em 6 secoes:\n"
        "## 1. Visao Geral do Mes\n## 2. Analise Comercial\n## 3. Pontos Fortes\n"
        "## 4. Desafios e Oportunidades\n## 5. Recomendacoes de Conteudo\n## 6. Proximos Passos\n\n"
        "Canais: " + str(p2.get("canais") or p2.get("funis","")) + "\n"
        "Objecoes: " + str(p2.get("objecoes","")) + "\n"
        "Historias: " + str(p3.get("historiasMes","")) + "\n"
        "Publico: " + str(p4.get("publicoAlvo","")) + "\n"
        "Diferencial: " + str(p4.get("diferencial",""))
    )
    return groq_call(prompt, max_tokens=1200)


def gerar_resumo_onboarding(dados, nome):
    p1=dados.get("pagina1",{}); p2=dados.get("pagina2",{})
    p3=dados.get("pagina3",{}); p4=dados.get("pagina4",{})
    p5=dados.get("pagina5",{}); p6=dados.get("pagina6",{})
    p7=dados.get("pagina7",{}); p8=dados.get("pagina8",{})
    prompt = (
        "Voce e uma estrategista de conteudo digital especializada em personal branding.\n"
        "Com base no onboarding do cliente abaixo, gere um resumo estrategico completo em portugues em 5 secoes:\n"
        "## 1. Perfil e Essencia\n"
        "## 2. Posicionamento e Diferenciais\n"
        "## 3. Publico e Comunicacao\n"
        "## 4. Identidade Visual e Tom de Voz\n"
        "## 5. Recomendacoes Estrategicas\n\n"
        "CLIENTE: " + nome + "\n"
        "Proposta: " + str(p1.get("proposta","")) + "\n"
        "Como comecou: " + str(p3.get("comeco","")) + "\n"
        "Publico: " + str(p3.get("publico","")) + "\n"
        "Diferencial: " + str(p3.get("diferencial","")) + "\n"
        "Nao acredita em: " + str(p3.get("naoAcredita","")) + "\n"
        "Quer falar sobre: " + str(p4.get("assuntosSim","")) + "\n"
        "Jamais falaria: " + str(p4.get("assuntosNao","")) + "\n"
        "O que funciona: " + str(p5.get("funciona","")) + "\n"
        "Desejo com perfil: " + str(p6.get("desejoPerfil","")) + "\n"
        "Servicos: " + str(p6.get("servicos","")) + "\n"
        "Identidade visual: " + str(p7.get("elementosVisuais","")) + "\n"
        "Universo da marca: " + str(p7.get("universoMarca","")) + "\n"
        "Tom de voz - formalidade: " + str(p8.get("formalidade","5")) + "/10\n"
        "Tom de voz - humor: " + str(p8.get("humor","5")) + "/10\n"
        "Cumprimentos: " + str(p8.get("cumprimentos",""))
    )
    return groq_call(prompt, max_tokens=1500)

def nb(tipo, content):
    return {"object":"block","type":tipo,tipo:{"rich_text":[{"type":"text","text":{"content":str(content)[:2000] if content else "-"}}]}}

def h2(t):  return nb("heading_2", t)
def h3(t):  return nb("heading_3", t)
def par(t): return nb("paragraph", t)
def li(label, val):
    return {"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":label + ": " + (str(val) if val else "-")}}]}}
def div():  return {"object":"block","type":"divider","divider":{}}

def blocos_mensal(d):
    p1=d.get("pagina1",{}); p2=d.get("pagina2",{})
    p3=d.get("pagina3",{}); p4=d.get("pagina4",{})
    bl = []
    bl.append(h2("Identificacao"))
    bl.append(li("Cliente", p1.get("nomeCliente") or p1.get("nome","")))
    bl.append(li("Pode gravar", p1.get("podeGravar","")))
    mat = p1.get("materiais",[])
    bl.append(li("Materiais", ", ".join(mat) if mat else "-"))
    if p1.get("dataGravacao"): bl.append(li("Data preferida", "Dia " + str(p1.get("dataGravacao",""))))
    if p1.get("obsGravacao") or p1.get("obsGeral"): bl.append(li("Obs", p1.get("obsGravacao") or p1.get("obsGeral","")))
    bl.append(div())
    bl.append(h2("Resultados Comerciais"))
    bl.append(li("Canais", p2.get("canais") or p2.get("funis","")))
    bl.append(li("Melhor canal", p2.get("melhorCanal") or p2.get("melhorFunil","")))
    if p2.get("callsAgendadas"): bl.append(li("Consultas", p2.get("callsAgendadas","")))
    if p2.get("vendasFechadas"): bl.append(li("Vendas", p2.get("vendasFechadas","")))
    if p2.get("ticketMedio"):    bl.append(li("Ticket medio", str(p2.get("ticketMedio",""))))
    bl.append(li("Objecoes", p2.get("objecoes","")))
    bl.append(li("Nao fechamentos", p2.get("naoFechamentos","")))
    if p2.get("destaqueMes"): bl.append(li("Destaque", p2.get("destaqueMes","")))
    if p2.get("descricaoOferta") or p2.get("servicos"):
        bl.append(h3("Servicos"))
        bl.append(par(p2.get("descricaoOferta") or p2.get("servicos","")))
    if p2.get("elogios"):   bl.append(li("Elogios", p2.get("elogios","")))
    if p2.get("melhorias"): bl.append(li("Melhorias", p2.get("melhorias","")))
    if p2.get("playlist"):  bl.append(li("Playlist", p2.get("playlist","")))
    bl.append(div())
    bl.append(h2("Historias e Conteudo"))
    bl.append(li("Historias", p3.get("historiasMes","")))
    bl.append(li("Resultados de clientes", p3.get("resultadosClientes") or p3.get("transformacoes","")))
    bl.append(li("Em destaque", p3.get("produtosDestaque") or p3.get("emDestaque","")))
    bl.append(li("Novidades", p3.get("novidades","")))
    bl.append(li("Temas", p3.get("temas","")))
    links = p3.get("links",[])
    if links:
        bl.append(h3("Links de referencia"))
        for lk in links:
            if lk: bl.append(par(lk))
    if p3.get("obsFinal"): bl.append(li("Obs finais", p3.get("obsFinal","")))
    bl.append(div())
    bl.append(h2("Negocio e Posicionamento"))
    bl.append(par(p4.get("historia","")))
    bl.append(li("Publico-alvo", p4.get("publicoAlvo","")))
    bl.append(li("Diferencial", p4.get("diferencial","")))
    if p4.get("naoAcredita"): bl.append(li("Nao acredita em", p4.get("naoAcredita","")))
    if p4.get("datasImportantes"): bl.append(li("Datas", p4.get("datasImportantes","")))
    bl.append(li("Tom de voz", str(p4.get("tomVoz","5")) + "/10"))
    if p4.get("tomVozDesc"): bl.append(par(p4.get("tomVozDesc","")))
    if p4.get("sonho"): bl.append(li("Sonho", p4.get("sonho","")))
    return bl

def blocos_onboarding(d):
    bl = []
    pgs = {("pagina"+str(i)): d.get("pagina"+str(i),{}) for i in range(1,9)}
    p1=pgs["pagina1"]; p2=pgs["pagina2"]; p3=pgs["pagina3"]; p4=pgs["pagina4"]
    p5=pgs["pagina5"]; p6=pgs["pagina6"]; p7=pgs["pagina7"]; p8=pgs["pagina8"]
    bl.append(h2("Identificacao"))
    bl.append(li("Nome", p1.get("nome","")))
    bl.append(par(p1.get("proposta","")))
    bl.append(div())
    bl.append(h2("Preferencias Pessoais"))
    for k,label in [("playlist","Playlist"),("youtube","YouTube"),("familia","Familia"),
                    ("adjetivos","Adjetivos"),("pessoas","Pessoas importantes"),("medo","Maior medo")]:
        if p2.get(k): bl.append(li(label, p2.get(k,"")))
    if p2.get("fatos"): bl.append(h3("5 fatos")); bl.append(par(p2.get("fatos","")))
    bl.append(div())
    bl.append(h2("Trabalho e Negocio"))
    bl.append(par(p3.get("comeco","")))
    if p3.get("sonho"): bl.append(li("Sonho de infancia", p3.get("sonho","")))
    bl.append(par(p3.get("publico","")))
    if p3.get("naoAcredita"): bl.append(li("Nao acredita em", p3.get("naoAcredita","")))
    if p3.get("diferencial"):  bl.append(li("Diferencial", p3.get("diferencial","")))
    bl.append(div())
    bl.append(h2("Conteudo e Redes Sociais"))
    for k,label in [("assuntosSim","Quer falar sobre"),("assuntosNao","Jamais falaria"),
                    ("concorrentes","Concorrentes"),("perfisNicho","Perfis do nicho"),
                    ("perfisReels","Perfis de reels"),("deixaSeguir","O que faz parar de seguir")]:
        if p4.get(k): bl.append(li(label, p4.get(k,"")))
    if p4.get("perfisNao"): bl.append(par(p4.get("perfisNao","")))
    bl.append(div())
    bl.append(h2("Perfil Proprio"))
    for k,label in [("funciona","O que funciona"),("naoDaCerto","O que nao da certo"),
                    ("ensaio","Ensaio fotografico"),("redesSociais","Outras redes")]:
        if p5.get(k): bl.append(li(label, p5.get(k,"")))
    if p5.get("favoritos"): bl.append(par(p5.get("favoritos","")))
    bl.append(div())
    bl.append(h2("Historias, Objetivo e Servicos"))
    if p6.get("historias"): bl.append(par(p6.get("historias","")))
    for k,label in [("desejoPerfil","Desejo com o perfil"),("expectativa","Expectativa"),
                    ("datasImportantes","Datas"),("provasSociais","Provas sociais")]:
        if p6.get(k): bl.append(li(label, p6.get(k,"")))
    if p6.get("servicos"): bl.append(par(p6.get("servicos","")))
    bl.append(div())
    bl.append(h2("Identidade Visual"))
    for k,label in [("idVisual","Identidade atual"),("artesAtuais","Artes atuais"),
                    ("elementoIncluir","Quer incluir"),("elementosVisuais","Gosta evita"),
                    ("perfisArte","Perfis de arte"),("corEvitar","Cor a evitar")]:
        if p7.get(k): bl.append(li(label, p7.get(k,"")))
    if p7.get("universoMarca"): bl.append(par(p7.get("universoMarca","")))
    bl.append(div())
    bl.append(h2("Tom de Voz"))
    for k,label in [("cumprimentos","Cumprimentos"),("adjetivosPositivos","Adjetivos positivos"),
                    ("adjetivosNegativos","Adjetivos negativos"),("agressividade","Agressividade"),
                    ("formalidade","Formalidade"),("humor","Humor"),("emojis","Emojis")]:
        if p8.get(k): bl.append(li(label, p8.get(k,"")))
    return bl

def salvar_no_notion(titulo, dados_orig, dados_pt, diagnostico, tipo, idioma):
    hoje_iso = datetime.now().strftime("%Y-%m-%d")
    dados_usar = dados_pt if dados_pt else dados_orig
    blocos = []
    if idioma == "en" and dados_pt:
        blocos.append(h2("Original Responses (English)"))
        for pg in ["pagina1","pagina2","pagina3","pagina4","pagina5","pagina6","pagina7","pagina8"]:
            sec = dados_orig.get(pg, {})
            for k, v in sec.items():
                if v and str(v).strip() and k != "idioma":
                    blocos.append(li(k, str(v)))
        blocos.append(div())
        blocos.append(h2("Traducao para o Portugues"))
    if tipo == "onboarding":
        blocos += blocos_onboarding(dados_usar)
    else:
        blocos += blocos_mensal(dados_usar)
    if diagnostico:
        label_diag = "Resumo Estrategico de Onboarding - IA" if tipo == "onboarding" else "Diagnostico Estrategico IA"
        blocos.append(h2(label_diag))
        for linha in diagnostico.split("\n"):
            linha = linha.strip()
            if not linha: continue
            if linha.startswith("## "): blocos.append(h3(linha.replace("## ","")))
            else: blocos.append(par(linha))
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"emoji": "📋"},
        "properties": {
            "Briefing": {"title": [{"text": {"content": titulo}}]},
            "Dia Recebido": {"date": {"start": hoje_iso}},
            "Status": {"select": {"name": "Nao usado"}},
        },
        "children": blocos[:100],
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=30)
    if r.status_code in (200, 201):
        page_id = r.json().get("id")
        if len(blocos) > 100:
            for i in range(100, len(blocos), 100):
                requests.patch(
                    "https://api.notion.com/v1/blocks/" + page_id + "/children",
                    headers=NOTION_HEADERS, json={"children": blocos[i:i+100]}, timeout=30
                )
        return {"page_id": page_id}
    else:
        print("[ERRO NOTION] " + str(r.status_code) + " - " + r.text[:300])
        return {"erro": r.text[:300]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
