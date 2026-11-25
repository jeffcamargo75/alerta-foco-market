"""Avisa no Telegram quando um evento POOL novo é cadastrado na Foco Market.

Cada execução: busca os eventos POOL futuros dos estados escolhidos, compara
com os já vistos (estado.json) e manda mensagem para os novos.
"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

import requests

SITE = "https://www.focomarket.com.br"
URL_API = SITE + "/next-api/competition/future-list"
URL_EVENTOS = SITE + "/competition/future"
# Página de um evento: {id} é trocado pelo número do evento.
LINK_EVENTO = SITE + "/competition/information?id={id}"
ARQUIVO_ESTADO = Path(__file__).with_name("estado.json")

# Estados monitorados: sigla -> código do estado na Foco Market.
# Para incluir outro, acrescente a sigla e o código desta lista:
# AC 38, AL 2, AP 3, AM 4, BA 5, CE 6, DF 7, ES 8, GO 9, MA 10, MT 11, MS 12, MG 13, PA 14,
# PB 15, PR 16, PE 17, PI 18, RJ 19, RN 20, RS 21, RO 22, RR 23, SC 24, SP 25, SE 26, TO 27
ESTADOS = {"PR": 16, "SC": 24}
NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
FOCO_COOKIE = os.environ.get("FOCO_COOKIE", "").strip()


class SessaoExpirada(Exception):
    pass


class SiteForaDoAr(Exception):
    """Site em manutenção ou instável (HTTP 5xx, 429, sem conexão). Costuma passar sozinho."""


# Site fora do ar por menos que isso: a execução fica verde e tenta de novo na próxima.
# Passou disso: fica vermelha (o GitHub manda e-mail) e avisa no Telegram uma vez.
LIMITE_FORA_DO_AR = timedelta(hours=6)


# ---------- Foco Market ----------

def limpar_cookie(bruto):
    """Aceita o valor copiado do navegador (com ou sem "cookie:" na frente)
    e descarta os cookies do Cloudflare, que só valem no navegador de origem."""
    if bruto.lower().startswith("cookie:"):
        bruto = bruto[len("cookie:"):]
    partes = [p.strip() for p in bruto.split(";") if "=" in p]
    return "; ".join(
        p for p in partes if not p.split("=", 1)[0].strip().lower().startswith(("__cf", "cf_"))
    )


def pedir_com_paciencia(sessao, params):
    """Faz a consulta; se o site estiver instável, tenta mais 2 vezes antes de desistir."""
    for espera in (15, 30, None):
        try:
            r = sessao.get(URL_API, params=params, timeout=30, allow_redirects=False)
            if r.status_code < 500 and r.status_code != 429:
                return r
            problema = f"HTTP {r.status_code}"
        except (requests.ConnectionError, requests.Timeout) as erro:
            problema = f"sem resposta ({type(erro).__name__})"
        if espera is None:
            raise SiteForaDoAr(problema)
        print(f"Foco Market instável ({problema}); tentando de novo em {espera}s.")
        time.sleep(espera)


def buscar_eventos_pool():
    sessao = requests.Session()
    sessao.headers.update({
        "User-Agent": NAVEGADOR,
        "Accept": "application/json",
        "Referer": URL_EVENTOS,
        "Cookie": limpar_cookie(FOCO_COOKIE),
    })
    # Sem data final a API só mostra os próximos 30 dias, e todo evento antigo
    # que entrasse nessa janela pareceria "novo". Por isso pede 2 anos à frente.
    ate = (date.today() + timedelta(days=730)).strftime("%d/%m/%Y")
    filtros = {
        "CompetitionSearch[is_spot]": "0",  # 0 = só eventos POOL
        "CompetitionSearch[future_list_date_to]": ate,
    }

    eventos = {}
    for codigo_estado in ESTADOS.values():
        pagina, total_paginas = 1, 1
        while pagina <= total_paginas:
            params = {**filtros, "CompetitionSearch[state_id]": codigo_estado, "page": pagina}
            r = pedir_com_paciencia(sessao, params)
            if r.is_redirect or (r.status_code in (401, 403) and "login" in r.text.lower()):
                raise SessaoExpirada()
            if r.status_code != 200:
                raise RuntimeError(f"Foco Market respondeu HTTP {r.status_code}: {r.text[:300]}")
            dados = r.json()
            for e in dados["items"]:
                eventos[e["id"]] = e
            total_paginas = dados["_meta"]["pageCount"]
            pagina += 1
            time.sleep(0.5)  # sem pressa: não sobrecarregar o site

    # Confere de novo aqui: mesmo se o site ignorar algum filtro, só passa POOL dos ESTADOS.
    return [
        e for e in eventos.values()
        if e.get("isPool") and (e.get("state") or {}).get("abbreviation") in ESTADOS
    ]


# ---------- Telegram ----------

def enviar_telegram(texto):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram não configurado — mensagem só no log]\n" + texto + "\n")
        return
    for _ in range(3):
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": texto,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=20,
        )
        if r.status_code == 429:  # muitas mensagens seguidas: o Telegram diz quanto esperar
            time.sleep(r.json().get("parameters", {}).get("retry_after", 5))
            continue
        if not r.ok:
            raise RuntimeError(f"Telegram respondeu HTTP {r.status_code}: {r.text[:300]}")
        time.sleep(1)
        return
    raise RuntimeError("Telegram recusou a mensagem 3 vezes seguidas (limite de envio).")


def formatar_evento(e):
    data = datetime.strptime(e["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
    local = e.get("place") or ""
    uf = (e.get("state") or {}).get("abbreviation")
    if uf:
        local = f"{local} / {uf}" if local else uf

    linhas = [f"<b>{escape(e['name'])}</b>", f"📅 {data}   📍 {escape(local)}"]
    esporte = (e.get("sport") or {}).get("name")
    selo = (e.get("partnershipBadge") or {}).get("label")
    detalhe = " · ".join(x for x in (esporte, selo) if x)
    if detalhe:
        linhas.append(escape(detalhe))

    vagas = e.get("eventSlotsAvailability")
    if vagas is not None:
        if vagas.get("availableSlots") is None:
            texto_vagas = "Vagas: livre"
        else:
            texto_vagas = f"Vagas restantes: {vagas['availableSlots']}"
        if vagas.get("minimumLevelName"):
            texto_vagas += f" (nível mínimo: {vagas['minimumLevelName']})"
        linhas.append("🎟 " + escape(texto_vagas))

    if e.get("formatedRegisterDate"):
        linhas.append(f"⏳ Cadastro até {escape(e['formatedRegisterDate'])}")
    link = LINK_EVENTO.format(id=e["id"])
    linhas.append(f'🔗 <a href="{escape(link)}">Abrir o evento</a>')
    return "\n".join(linhas)


def avisar_novos(novos):
    # Até 5 eventos: uma mensagem cada. Mais que isso (cadastro em lote): agrupa de 10 em 10.
    tamanho = 1 if len(novos) <= 5 else 10
    for i in range(0, len(novos), tamanho):
        grupo = novos[i:i + tamanho]
        titulo = "🏁 <b>Novo evento POOL na Foco Market</b>" if len(grupo) == 1 else (
            f"🏁 <b>{len(grupo)} novos eventos POOL na Foco Market</b>"
        )
        corpo = "\n\n".join(formatar_evento(e) for e in grupo)
        enviar_telegram(f"{titulo}\n\n{corpo}")
        yield grupo


# ---------- Estado ----------

def carregar_estado():
    if ARQUIVO_ESTADO.exists():
        return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    return {"vistos": None, "avisou_sessao_expirada": False}


def salvar_estado(estado):
    ARQUIVO_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------- Principal ----------

def main():
    if not FOCO_COOKIE:
        sys.exit("Falta o secret FOCO_COOKIE (veja o LEIA-ME.md).")

    estado = carregar_estado()
    try:
        eventos = buscar_eventos_pool()
    except SessaoExpirada:
        if not estado["avisou_sessao_expirada"]:
            enviar_telegram(
                "⚠️ <b>A sessão da Foco Market expirou.</b>\n"
                "O alerta está parado. Entre de novo no site marcando \"Lembre-me\" e "
                "atualize o secret FOCO_COOKIE no GitHub (passo 3 do LEIA-ME)."
            )
            estado["avisou_sessao_expirada"] = True
            salvar_estado(estado)
        sys.exit("Sessão da Foco Market expirada: atualize o FOCO_COOKIE.")
    except SiteForaDoAr as erro:
        agora = datetime.now(timezone.utc)
        if not estado.get("fora_do_ar_desde"):
            estado["fora_do_ar_desde"] = agora.isoformat(timespec="seconds")
            salvar_estado(estado)
        tempo = agora - datetime.fromisoformat(estado["fora_do_ar_desde"])
        horas = tempo.total_seconds() / 3600
        if tempo < LIMITE_FORA_DO_AR:
            print(f"Foco Market fora do ar ({erro}) há {horas:.1f} h. "
                  "Normal em manutenção: tenta de novo na próxima execução.")
            return
        if not estado.get("avisou_fora_do_ar"):
            enviar_telegram(
                f"⚠️ <b>A Foco Market está fora do ar há {horas:.0f} horas.</b>\n"
                "O alerta continua tentando e avisa aqui quando o site voltar."
            )
            estado["avisou_fora_do_ar"] = True
            salvar_estado(estado)
        sys.exit(f"Foco Market fora do ar ({erro}) há {horas:.0f} horas.")

    if estado.get("fora_do_ar_desde"):
        avisou = estado.pop("avisou_fora_do_ar", False)
        del estado["fora_do_ar_desde"]
        salvar_estado(estado)
        if avisou:
            enviar_telegram("✅ A Foco Market voltou. O alerta está funcionando de novo.")

    if not eventos:
        sys.exit(f"Nenhum evento POOL em {'/'.join(ESTADOS)} veio da API — o site pode ter mudado.")

    if estado["avisou_sessao_expirada"]:
        estado["avisou_sessao_expirada"] = False
        salvar_estado(estado)
        enviar_telegram("✅ Sessão da Foco Market renovada. O alerta voltou a funcionar.")

    if estado["vistos"] is None:
        estado["vistos"] = sorted(str(e["id"]) for e in eventos)
        salvar_estado(estado)
        enviar_telegram(
            f"✅ <b>Alerta ativado ({'/'.join(ESTADOS)}).</b>\n{len(eventos)} eventos POOL já "
            f"cadastrados na Foco Market em {' e '.join(ESTADOS)}. "
            "A partir de agora aviso aqui cada evento POOL novo desses estados."
        )
        print(f"Primeira execução: {len(eventos)} eventos POOL registrados.")
        return

    vistos = set(estado["vistos"])
    novos = sorted(
        (e for e in eventos if str(e["id"]) not in vistos),
        key=lambda e: (e["date"], e["name"]),
    )
    for grupo in avisar_novos(novos):
        # Salva a cada envio: se algo falhar no meio, não repete o que já foi avisado.
        vistos.update(str(e["id"]) for e in grupo)
        estado["vistos"] = sorted(vistos)
        salvar_estado(estado)

    print(f"{len(eventos)} eventos POOL na Foco Market, {len(novos)} novos.")


if __name__ == "__main__":
    main()
