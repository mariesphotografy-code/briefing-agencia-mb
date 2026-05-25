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

# ─────────────────────────────────────────────
# ROTA DE HEALTH CHECK
# ─────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agencia MB Briefing Mensal - online"})


# ─────────────────────────────────────────────
# ROTA PRINCIPAL DO WEBHOOK
# ─────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.form.get("dados")
        if not raw:
            return jsonify({"erro": "Campo 'dados' não encontrado"}), 400

        dados = json.loads(raw)

        p1 = dados.get("pagina1", {})
        p2 = dados.get("pagina2", {})
        p3 = dados.get("pagina3", {})
        p4 = dados.get("pagina4", {})

        nome_cliente  = p1.get("nomeCliente", "Cliente")
        mes_referencia = p1.get("mesReferencia", "")
        hoje = datetime.now().strftime("%d/%m/%Y")

        titulo_pagina = f"Briefing {nome_cliente} — {hoje}"

        # 1. Gerar diagnóstico com Groq
        diagnostico = gerar_diagnostico(dados, nome_cliente, mes_referencia)

        # 2. Salvar no Notion
        resultado = salvar_no_notion(
            titulo=titulo_pagina,
            dados=dados,
            diagnostico=diagnostico,
            p1=p1, p2=p2, p3=p3, p4=p4
        )

        return jsonify({"status": "ok", "notion": resultado}), 200

    except Exception as e:
        print(f"[ERRO WEBHOOK] {e}")
        return jsonify({"erro": str(e)}), 500


# ─────────────────────────────────────────────
# GROQ — DIAGNÓSTICO ESTRATÉGICO
# ─────────────────────────────────────────────
def gerar_diagnostico(dados, nome, mes):
    p2 = dados.get("pagina2", {})
    p3 = dados.get("pagina3", {})
    p4 = dados.get("pagina4", {})

    prompt = f"""
Você é um consultor estratégico de conteúdo digital especializado em profissionais de saúde e estética.

Analise o briefing mensal do cliente abaixo e gere um diagnóstico estratégico completo em português, estruturado em 6 seções claras.

DADOS DO CLIENTE: {nome} | Mês: {mes}

DADOS COMERCIAIS:
- Funis utilizados: {p2.get('funis', 'não informado')}
- Melhor funil: {p2.get('melhorFunil', 'não informado')}
- Calls agendadas: {p2.get('callsAgendadas', 'não informado')}
- Vendas fechadas: {p2.get('vendasFechadas', 'não informado')}
- Ticket médio: R$ {p2.get('ticketMedio', 'não informado')}
- Taxa de conversão: {p2.get('taxaConversao', 'não informado')}%
- Principais objeções: {p2.get('objecoes', 'não informado')}
- Motivo dos não-fechamentos: {p2.get('naoFechamentos', 'não informado')}
- Destaque do mês: {p2.get('destaqueMes', 'não informado')}
- Tipo de oferta: {p2.get('tipoOferta', 'não informado')}
- Serviços/Produtos: {p2.get('descricaoOferta', 'não informado')}

CONTEÚDO E HISTÓRIAS:
- Histórias do mês: {p3.get('historiasMes', 'não informado')}
- Resultados de clientes: {p3.get('resultadosClientes', 'não informado')}
- Novidades/Lançamentos: {p3.get('novidades', 'não informado')}
- Temas para conteúdo: {p3.get('temas', 'não informado')}

NEGÓCIO E POSICIONAMENTO:
- História do profissional: {p4.get('historia', 'não informado')}
- Público-alvo: {p4.get('publicoAlvo', 'não informado')}
- Diferencial: {p4.get('diferencial', 'não informado')}
- Tom de voz (0=formal / 10=informal): {p4.get('tomVoz', 'não informado')}
- Descrição do tom: {p4.get('tomVozDesc', 'não informado')}

---

Gere o diagnóstico em 6 seções com este formato exato:

## 1. Visão Geral do Mês
[Resumo do momento do negócio, performance geral e contexto estratégico]

## 2. Análise Comercial
[Interpretação dos números: calls, vendas, conversão, ticket. Padrões e gaps identificados]

## 3. Pontos Fortes
[O que está funcionando bem e deve ser mantido ou amplificado no conteúdo]

## 4. Desafios e Oportunidades
[Problemas identificados nas objeções e não-fechamentos + oportunidades não exploradas]

## 5. Recomendações de Conteúdo
[3 a 5 direcionamentos específicos de conteúdo para o próximo mês, alinhados ao tom de voz e público]

## 6. Próximos Passos Prioritários
[2 a 3 ações concretas e urgentes para o time de conteúdo executar]

Seja direto, estratégico e específico. Evite generalidades. Use os dados fornecidos como base real para cada análise.
"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.7,
            },
            timeout=60,
        )
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Diagnóstico não gerado — erro: {e}]"


# ─────────────────────────────────────────────
# NOTION — SALVAR PÁGINA
# ─────────────────────────────────────────────
def salvar_no_notion(titulo, dados, diagnostico, p1, p2, p3, p4):
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    # ── Monta blocos de conteúdo ──────────────────
    blocos = []

    def heading(texto, level=2):
        tipo = f"heading_{level}"
        return {
            "object": "block",
            "type": tipo,
            tipo: {"rich_text": [{"type": "text", "text": {"content": texto}}]}
        }

    def paragrafo(texto):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": str(texto) if texto else "—"}}]}
        }

    def linha(label, valor):
        conteudo = f"{label}: {valor if valor else '—'}"
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": conteudo}}]}
        }

    def divisor():
        return {"object": "block", "type": "divider", "divider": {}}

    # SEÇÃO 1 — Identificação
    blocos.append(heading("📋 Identificação e Gravação"))
    blocos.append(linha("Cliente", p1.get("nomeCliente")))
    blocos.append(linha("Mês de referência", p1.get("mesReferencia")))
    blocos.append(linha("Pode gravar", p1.get("podeGravar")))
    materiais = p1.get("materiais", [])
    blocos.append(linha("Materiais disponíveis", ", ".join(materiais) if materiais else "—"))
    blocos.append(linha("Data preferida de gravação", f"Dia {p1.get('dataGravacao')}" if p1.get("dataGravacao") else "—"))
    obs_grav = p1.get("obsGravacao")
    if obs_grav:
        blocos.append(linha("Observações sobre gravação", obs_grav))
    blocos.append(divisor())

    # SEÇÃO 2 — Comercial
    blocos.append(heading("💰 Dados Comerciais"))
    blocos.append(linha("Funis utilizados", p2.get("funis")))
    blocos.append(linha("Melhor funil", p2.get("melhorFunil")))
    blocos.append(linha("Calls agendadas", p2.get("callsAgendadas")))
    blocos.append(linha("Vendas fechadas", p2.get("vendasFechadas")))
    blocos.append(linha("Ticket médio", f"R$ {p2.get('ticketMedio')}" if p2.get("ticketMedio") else "—"))
    blocos.append(linha("Taxa de conversão", f"{p2.get('taxaConversao')}%" if p2.get("taxaConversao") else "—"))
    blocos.append(linha("Principais objeções", p2.get("objecoes")))
    blocos.append(linha("Motivo dos não-fechamentos", p2.get("naoFechamentos")))
    blocos.append(linha("Destaque do mês", p2.get("destaqueMes")))
    blocos.append(linha("Tipo de oferta", p2.get("tipoOferta")))
    if p2.get("descricaoOferta"):
        blocos.append(heading("Serviços / Produtos", 3))
        blocos.append(paragrafo(p2.get("descricaoOferta")))
    if p2.get("playlist"):
        blocos.append(linha("Playlist", p2.get("playlist")))
    blocos.append(divisor())

    # SEÇÃO 3 — Conteúdo
    blocos.append(heading("🎬 Histórias e Conteúdo"))
    blocos.append(linha("Histórias do mês", p3.get("historiasMes")))
    blocos.append(linha("Resultados de clientes", p3.get("resultadosClientes")))
    blocos.append(linha("Produtos/serviços em destaque", p3.get("produtosDestaque")))
    blocos.append(linha("Novidades/lançamentos", p3.get("novidades")))
    blocos.append(linha("Temas para o conteúdo", p3.get("temas")))
    links = p3.get("links", [])
    if links:
        blocos.append(heading("Links de referência", 3))
        for link in links:
            if link:
                blocos.append(paragrafo(link))
    if p3.get("obsFinal"):
        blocos.append(linha("Observações finais", p3.get("obsFinal")))
    blocos.append(divisor())

    # SEÇÃO 4 — Negócio
    blocos.append(heading("🏢 Negócio e Posicionamento"))
    blocos.append(heading("História do profissional", 3))
    blocos.append(paragrafo(p4.get("historia")))
    blocos.append(linha("Público-alvo", p4.get("publicoAlvo")))
    blocos.append(linha("No que não acredita no nicho", p4.get("naoAcredita")))
    blocos.append(linha("Diferencial", p4.get("diferencial")))
    blocos.append(linha("Datas importantes", p4.get("datasImportantes")))
    tom = p4.get("tomVoz", "5")
    tom_desc = "Formal" if int(tom) <= 3 else ("Equilibrado" if int(tom) <= 7 else "Informal")
    blocos.append(linha("Tom de voz", f"{tom}/10 — {tom_desc}"))
    if p4.get("tomVozDesc"):
        blocos.append(paragrafo(p4.get("tomVozDesc")))
    blocos.append(divisor())

    # SEÇÃO 5 — Diagnóstico de IA
    blocos.append(heading("🤖 Diagnóstico Estratégico — IA"))
    # Quebra o diagnóstico em parágrafos para caber nos blocos do Notion
    for linha_diag in diagnostico.split("\n"):
        linha_diag = linha_diag.strip()
        if not linha_diag:
            continue
        if linha_diag.startswith("## "):
            blocos.append(heading(linha_diag.replace("## ", ""), 3))
        elif len(linha_diag) <= 2000:
            blocos.append(paragrafo(linha_diag))
        else:
            # Divide parágrafos muito longos
            for i in range(0, len(linha_diag), 2000):
                blocos.append(paragrafo(linha_diag[i:i+2000]))

    # ── Cria a página no Notion ───────────────────
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"emoji": "📬"},
        "properties": {
            "Briefing": {
                "title": [{"text": {"content": titulo}}]
            },
            "Dia Recebido": {
                "date": {"start": hoje_iso}
            },
            "Status": {
                "select": {"name": "Não usado"}
            },
        },
        "children": blocos[:100],  # Notion aceita até 100 blocos por request
    }

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json=payload,
        timeout=30,
    )

    if r.status_code in (200, 201):
        page_id = r.json().get("id")
        # Se houver mais blocos, adiciona em chamadas extras
        if len(blocos) > 100:
            adicionar_blocos_extras(page_id, blocos[100:])
        return {"page_id": page_id, "url": r.json().get("url")}
    else:
        print(f"[ERRO NOTION] {r.status_code} — {r.text}")
        return {"erro": r.text}


def adicionar_blocos_extras(page_id, blocos_extras):
    """Adiciona blocos restantes em lotes de 100."""
    for i in range(0, len(blocos_extras), 100):
        lote = blocos_extras[i:i+100]
        requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": lote},
            timeout=30,
        )


# ─────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
