# Betsniper

Dashboard local para futebol com dados ESPN e odds via Betfair/coletores.

## Rodar agora

Abra o PowerShell na raiz do projeto:

```powershell
cd C:\Users\vini\Documents\Betsniper
```

Garanta que o `.env` existe:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Atualize dependencias e o navegador do Playwright:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Inicialize/migre o banco:

```powershell
.\.venv\Scripts\python.exe -c "from src.db.session import init_db; init_db()"
```

Para executar o projeto completo, coletando ESPN/Betfair e depois abrindo o dashboard:

```powershell
.\.venv\Scripts\python.exe scripts\run_project.py
```

Esse comando coleta o dia base e o dia seguinte. Se voce passar uma data, ele coleta essa data e a proxima:

```powershell
.\.venv\Scripts\python.exe scripts\run_project.py --date 2026-05-13
```

Depois acesse:

```text
http://127.0.0.1:8501
```

Se voce quiser apenas abrir o dashboard sem coletar dados antes:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501
```

O dashboard mostra sempre duas secoes retrateis em cada aba: `Hoje` e `Amanha`.

Depois acesse:

```text
http://127.0.0.1:8501
```

Se a porta `8501` ja estiver em uso, rode em outra:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.port 8502
```

## Primeiro setup

Use esta secao apenas se a pasta `.venv` nao existir.

```powershell
cd C:\Users\vini\Documents\Betsniper
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Se `py` nao existir, instale o Python para Windows e habilite o Python Launcher ou adicione o Python ao PATH.

## Configuracao

Edite `.env` conforme necessario. O banco padrao e:

```text
APP_DB_URL=sqlite:///data/betsniper.db
APP_TIMEZONE=America/Sao_Paulo
```

Configuracao Betfair padrao:

```text
BETFAIR_WEB_ENABLED=true
BETFAIR_WEB_HEADLESS=true
BETFAIR_AUTO_LOGIN=true
BETFAIR_USERNAME=seu_usuario_ou_email
BETFAIR_PASSWORD=sua_senha
BETFAIR_ALLOW_GEOLOCATION=true
BETFAIR_GEO_LATITUDE=sua_latitude_real
BETFAIR_GEO_LONGITUDE=sua_longitude_real
BETFAIR_GEO_ACCURACY=100
BETFAIR_GEO_JITTER_METERS=30
BETFAIR_LOGIN_TIMEOUT_SECONDS=120
BETFAIR_BASE_URL=https://www.betfair.bet.br/apostas/
BETFAIR_COMPETITION_URL=https://www.betfair.com/sport/football
BETFAIR_STORAGE_STATE=data/betfair_storage_state.json
BETFAIR_EVENT_URLS_FILE=data/betfair_event_urls.json
ODDS_STALE_AFTER_HOURS=12
```

`BETFAIR_USERNAME`, `BETFAIR_PASSWORD`, `BETFAIR_GEO_LATITUDE` e `BETFAIR_GEO_LONGITUDE` ficam somente no seu `.env`, que esta no `.gitignore`.

## X.com

Para publicar os mercados da aba `Barbadas do Dia`, configure no `.env`:

```text
X_API_BASE_URL=https://api.x.com
X_API_KEY=sua_api_key
X_API_KEY_SECRET=seu_api_key_secret
X_ACCESS_TOKEN=seu_access_token
X_ACCESS_TOKEN_SECRET=seu_access_token_secret
X_POST_DELAY_SECONDS=60
X_POST_MAX_CHARS=280
X_PUBLISH_PASSWORD=sua_senha_para_liberar_publicacao
```

Abra `Barbadas do Dia`, clique no botao escondido acima do titulo `Betsniper`, digite `X_PUBLISH_PASSWORD` e entao publique. O dashboard cria 1 post por aposta e espera `X_POST_DELAY_SECONDS` entre posts.

Se a Betfair exigir captcha, 2FA ou alguma confirmacao visual, use temporariamente:

```text
BETFAIR_WEB_HEADLESS=false
```

Assim o navegador abre, o sistema preenche usuario/senha, libera geolocalizacao e voce consegue concluir o desafio manualmente. Ao concluir, a sessao e salva em `data/betfair_storage_state.json`.

O `BETFAIR_GEO_JITTER_METERS` aplica uma variacao aleatoria de ate 30 metros nas coordenadas antes de abrir a Betfair.

## Rodar ETL

Para coletar o dia atual e o proximo dia, incluindo Betfair quando `BETFAIR_WEB_ENABLED=true`:

```powershell
.\.venv\Scripts\python.exe main.py
```

Para uma data especifica e o dia seguinte:

```powershell
.\.venv\Scripts\python.exe main.py --date YYYY-MM-DD
```

Para coletar apenas uma data:

```powershell
.\.venv\Scripts\python.exe main.py --date YYYY-MM-DD --days 1
```

Para atualizar ESPN/historico sem odds:

```powershell
.\.venv\Scripts\python.exe main.py --skip-odds
```

## Betfair web

O login automatico roda durante `main.py` e `scripts\run_project.py` quando `BETFAIR_AUTO_LOGIN=true` e as credenciais existem no `.env`.

Para forcar ou renovar a sessao local manualmente:

```powershell
.\.venv\Scripts\python.exe scripts\betfair_login.py
```

Se precisar mapear URLs manualmente:

```powershell
Copy-Item data\betfair_event_urls.example.json data\betfair_event_urls.json
```

Teste o coletor:

```powershell
.\.venv\Scripts\python.exe scripts\probe_betfair_web.py --date YYYY-MM-DD
```

## Testes

O projeto usa `unittest`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Problemas comuns

Se aparecer `python not found`, nao use `python` direto. Use:

```powershell
.\.venv\Scripts\python.exe
```

Se aparecer `streamlit not recognized`, nao use `streamlit` direto. Use:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501
```

Se quiser que a coleta Betfair rode sempre antes do dashboard, use:

```powershell
.\.venv\Scripts\python.exe scripts\run_project.py
```

Se aparecer erro de coluna ausente no SQLite, rode a migracao:

```powershell
.\.venv\Scripts\python.exe -c "from src.db.session import init_db; init_db()"
```

Se o dashboard avisar odds stale, rode o ETL antes de usar as odds:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Task Scheduler

Programa:

```text
C:\Users\vini\Documents\Betsniper\.venv\Scripts\python.exe
```

Argumentos:

```text
C:\Users\vini\Documents\Betsniper\main.py
```

Iniciar em:

```text
C:\Users\vini\Documents\Betsniper
```
