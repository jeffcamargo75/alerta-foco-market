# Alerta de eventos POOL da Foco Market no Telegram

A cada 15 minutos o GitHub consulta a Foco Market com a sua sessão, pega **só os eventos POOL**
futuros e manda no Telegram cada evento novo: nome, data, cidade, vagas, nível mínimo e prazo de cadastro.

Por que não usa sua senha: o login da Foco Market tem captcha, e robô não passa por captcha.
Então você faz o login uma vez no navegador e entrega ao robô o **cookie da sessão**
(como se o robô fosse uma aba sua já logada).

## 1. Criar o bot do Telegram (2 minutos)

1. No Telegram, abra uma conversa com **@BotFather** (tem o selo azul de verificado).
2. Envie `/newbot`.
3. Ele pede um **nome** de exibição: por exemplo `Alerta Foco Market`.
4. Depois pede um **username**, que precisa terminar em `bot`: por exemplo `alerta_foco_market_bot`.
   Se já existir, tente outro.
5. Ele responde com um **token** parecido com `123456789:AAH...`. Esse token é a senha do bot:
   guarde e não mande para ninguém.

## 2. Descobrir o seu chat_id

1. Abra a conversa com o seu bot novo (o BotFather manda o link `t.me/...`) e toque em **Iniciar**.
   - Se quiser o alerta num **grupo**: adicione o bot ao grupo e mande uma mensagem lá.
2. No navegador, abra (trocando `SEU_TOKEN` pelo token):
   `https://api.telegram.org/botSEU_TOKEN/getUpdates`
3. Procure `"chat":{"id":` — o número logo depois é o **chat_id**
   (em grupo ele começa com `-`, mantenha o sinal).

## 3. Copiar o cookie da Foco Market

Faça no Chrome do computador:

1. Abra uma **janela anônima** (Ctrl+Shift+N).
2. Entre em www.focomarket.com.br **marcando "Lembre-me"**.
3. Abra `https://www.focomarket.com.br/competition/future`.
4. Aperte **F12**, clique na aba **Network** (ou **Rede**) e aperte **F5** para recarregar.
5. Na caixa **Filter** (Filtro), digite `future-list` e clique na linha que aparecer.
6. Em **Headers** (Cabeçalhos) → **Request Headers**, ache a linha **cookie**,
   clique com o botão direito → **Copy value** (Copiar valor).
7. Feche a janela anônima **sem clicar em Sair** (sair encerra a sessão que o robô vai usar).

Esse valor dá acesso à sua conta: cole só no GitHub (passo 4), nunca em conversa ou e-mail.

Quando a sessão expirar, o bot manda no Telegram "⚠️ A sessão da Foco Market expirou".
É só repetir este passo 3 e atualizar o secret `FOCO_COOKIE`. Quando voltar, ele avisa
e manda os eventos que apareceram enquanto estava parado.

## 4. Colocar no GitHub

1. Crie uma conta em github.com (se não tiver) e um repositório novo (veja abaixo: público ou privado).
2. Envie os arquivos desta pasta: `monitor.py`, `requirements.txt` e a pasta `.github`.
3. No repositório: **Settings → Secrets and variables → Actions → New repository secret** e crie:

   | Nome | Valor |
   |---|---|
   | `TELEGRAM_TOKEN` | o token do BotFather (passo 1) |
   | `TELEGRAM_CHAT_ID` | o chat_id (passo 2) |
   | `FOCO_COOKIE` | o cookie copiado (passo 3) |

   Os secrets ficam criptografados: ninguém vê depois de salvos, nem em repositório público.
4. Vá em **Actions → Alerta de eventos POOL → Run workflow** para testar.
   Na primeira vez chega no Telegram "✅ Alerta ativado. N eventos POOL já cadastrados".
   Daí em diante, só chega mensagem quando aparece evento POOL novo.

## Público ou privado? (custo zero nos dois)

Cada verificação leva menos de 1 minuto, mas o GitHub cobra 1 minuto cheio.

- **Público:** minutos ilimitados, pode verificar a cada 15 minutos (ou até a cada 5).
  O código e a lista de IDs de eventos já vistos ficam visíveis; os secrets não.
  Se ficar 60 dias sem nenhum evento novo, o GitHub pausa o agendamento e manda e-mail
  (difícil acontecer: aparecem eventos toda semana).
- **Privado:** só você vê tudo, mas o grátis é 2.000 minutos/mês. A cada 15 minutos daria ~2.900,
  então mude o `cron` em `.github/workflows/alerta.yml` para `"*/30 * * * *"` (a cada 30 minutos).

O GitHub pode atrasar a execução alguns minutos em horários de pico.
Se algo der errado (site mudou, bloqueio, sessão), a execução fica vermelha e o GitHub manda e-mail.
